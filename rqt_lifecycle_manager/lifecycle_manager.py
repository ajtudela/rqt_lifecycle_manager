# Copyright (c) 2026 Alberto Tudela
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Asynchronous ROS 2 backend for the rqt Lifecycle Manager plugin.

This module wraps an ``rclpy`` node to discover lifecycle nodes and to query
and change their states. Every service interaction uses ``call_async`` and
delivers its outcome through result callbacks, so the caller (the Qt GUI
thread) is never blocked waiting for a response.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Set, Tuple

from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetAvailableTransitions, GetState
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.client import Client
from rclpy.node import Node

# Type aliases for the result callbacks used to marshal data back to the GUI.
StateCallback = Callable[[str, int, str], None]
TransitionsCallback = Callable[[str, List[Tuple[int, str, str]]], None]
ChangeStateCallback = Callable[[str, bool, str], None]

# Service name suffixes exposed by every ROS 2 lifecycle node.
GET_STATE_SUFFIX = '/get_state'
CHANGE_STATE_SUFFIX = '/change_state'
GET_AVAILABLE_TRANSITIONS_SUFFIX = '/get_available_transitions'

# Fully-qualified service type used to recognize a lifecycle node.
GET_STATE_SRV_TYPE = 'lifecycle_msgs/srv/GetState'


class LifecycleManager:
    """
    Discover and control ROS 2 lifecycle nodes without blocking the caller.

    The manager reuses an externally-owned ``rclpy`` node (the one provided by
    ``rqt_gui_py`` and spun in a background executor thread). Service clients
    are created lazily and cached per lifecycle node. All requests are issued
    with ``call_async`` and their results are forwarded to the supplied
    callbacks from the executor thread.

    Parameters
    ----------
    node : rclpy.node.Node
        The ROS 2 node used to query the graph and create service clients.

    """

    def __init__(self, node: Node) -> None:
        """
        Initialize the manager with an existing ROS 2 node.

        Parameters
        ----------
        node : rclpy.node.Node
            The ROS 2 node used for graph queries and service clients.

        """
        self._node = node
        # A reentrant group lets several requests be in flight concurrently.
        self._callback_group = ReentrantCallbackGroup()
        self._get_state_clients: Dict[str, Client] = {}
        self._change_state_clients: Dict[str, Client] = {}
        self._get_transitions_clients: Dict[str, Client] = {}
        # Keys of polling requests currently in flight, to avoid flooding.
        self._pending: Set[Tuple[str, str]] = set()

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    def get_lifecycle_node_names(self) -> List[str]:
        """
        Return the sorted names of every lifecycle node on the graph.

        A node is considered a lifecycle node when it exposes a
        ``<node>/get_state`` service of type ``lifecycle_msgs/srv/GetState``.
        This is a fast, local graph query and does not block on the network.

        Returns
        -------
        List[str]
            Fully-qualified names of the discovered lifecycle nodes.

        """
        node_names: List[str] = []
        for name, types in self._node.get_service_names_and_types():
            if name.endswith(GET_STATE_SUFFIX) and GET_STATE_SRV_TYPE in types:
                node_names.append(name[: -len(GET_STATE_SUFFIX)])
        return sorted(node_names)

    # -------------------------------------------------------------------------
    # Asynchronous requests
    # -------------------------------------------------------------------------

    def async_get_state(
        self, node_name: str, on_result: StateCallback
    ) -> None:
        """
        Request the current state of a lifecycle node asynchronously.

        Parameters
        ----------
        node_name : str
            Fully-qualified name of the target lifecycle node.
        on_result : StateCallback
            Called from the executor thread as ``(node_name, state_id,
            state_label)`` when the response arrives.

        """
        key = (node_name, 'state')
        if key in self._pending:
            return
        client = self._client(
            self._get_state_clients, node_name, GET_STATE_SUFFIX, GetState)
        if not client.service_is_ready():
            return
        self._pending.add(key)
        future = client.call_async(GetState.Request())
        future.add_done_callback(
            lambda f: self._on_state_response(node_name, f, on_result, key))

    def async_get_available_transitions(
        self, node_name: str, on_result: TransitionsCallback
    ) -> None:
        """
        Request the available transitions of a lifecycle node.

        Parameters
        ----------
        node_name : str
            Fully-qualified name of the target lifecycle node.
        on_result : TransitionsCallback
            Called from the executor thread as ``(node_name, transitions)``
            where ``transitions`` is a list of ``(id, label, goal_label)``.

        """
        key = (node_name, 'transitions')
        if key in self._pending:
            return
        client = self._client(
            self._get_transitions_clients, node_name,
            GET_AVAILABLE_TRANSITIONS_SUFFIX, GetAvailableTransitions)
        if not client.service_is_ready():
            return
        self._pending.add(key)
        future = client.call_async(GetAvailableTransitions.Request())
        future.add_done_callback(
            lambda f: self._on_transitions_response(
                node_name, f, on_result, key))

    def async_change_state(
        self, node_name: str, transition_id: int,
        on_result: ChangeStateCallback
    ) -> None:
        """
        Trigger a lifecycle transition asynchronously.

        Parameters
        ----------
        node_name : str
            Fully-qualified name of the target lifecycle node.
        transition_id : int
            Identifier of the transition to trigger (``lifecycle_msgs`` id).
        on_result : ChangeStateCallback
            Called from the executor thread as ``(node_name, success,
            message)`` once the transition completes or fails.

        """
        client = self._client(
            self._change_state_clients, node_name,
            CHANGE_STATE_SUFFIX, ChangeState)
        if not client.service_is_ready():
            on_result(node_name, False, 'change_state service not available')
            return
        request = ChangeState.Request()
        request.transition = Transition(id=transition_id)
        future = client.call_async(request)
        future.add_done_callback(
            lambda f: self._on_change_state_response(node_name, f, on_result))

    # -------------------------------------------------------------------------
    # Lifecycle of the manager itself
    # -------------------------------------------------------------------------

    def shutdown(self) -> None:
        """Destroy every cached service client and clear internal state."""
        for cache in (
            self._get_state_clients,
            self._change_state_clients,
            self._get_transitions_clients,
        ):
            for client in cache.values():
                self._node.destroy_client(client)
            cache.clear()
        self._pending.clear()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _client(
        self, cache: Dict[str, Client], node_name: str, suffix: str,
        srv_type: type
    ) -> Client:
        """Return a cached service client, creating it on first use."""
        client = cache.get(node_name)
        if client is None:
            client = self._node.create_client(
                srv_type, node_name + suffix,
                callback_group=self._callback_group)
            cache[node_name] = client
        return client

    def _on_state_response(
        self, node_name: str, future, on_result: StateCallback,
        key: Tuple[str, str]
    ) -> None:
        """Forward the get_state response, guarding against failures."""
        self._pending.discard(key)
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001 - surface any service error
            self._node.get_logger().warn(
                f'get_state failed for {node_name}: {exc}')
            return
        state = response.current_state
        on_result(node_name, state.id, state.label)

    def _on_transitions_response(
        self, node_name: str, future, on_result: TransitionsCallback,
        key: Tuple[str, str]
    ) -> None:
        """Forward the available-transitions response as simple tuples."""
        self._pending.discard(key)
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001 - surface any service error
            self._node.get_logger().warn(
                f'get_available_transitions failed for {node_name}: {exc}')
            return
        transitions = [
            (item.transition.id, item.transition.label, item.goal_state.label)
            for item in response.available_transitions
        ]
        on_result(node_name, transitions)

    def _on_change_state_response(
        self, node_name: str, future, on_result: ChangeStateCallback
    ) -> None:
        """Forward the change_state outcome, guarding against failures."""
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001 - surface any service error
            on_result(node_name, False, str(exc))
            return
        on_result(node_name, response.success, '')
