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
Unit tests for the LifecycleManager backend.

The manager only talks to ROS 2 through a node handle, so the tests drive it
with lightweight stubs for the node, its service clients and their futures.
This keeps the suite headless and independent of a live ROS 2 graph, while
still exercising the real asynchronous code paths (including the callbacks
that would normally run on the executor thread).
"""

from lifecycle_msgs.msg import State, Transition, TransitionDescription
from lifecycle_msgs.srv import ChangeState, GetAvailableTransitions, GetState
import pytest
from rqt_lifecycle_manager.lifecycle_manager import LifecycleManager


class _FakeFuture:
    """Stub of an rclpy future whose completion the test triggers."""

    def __init__(self):
        """Start with no result, no exception and no callbacks."""
        self._callbacks = []
        self._result = None
        self._exception = None

    def add_done_callback(self, callback):
        """Register a callback to run when the future completes."""
        self._callbacks.append(callback)

    def result(self):
        """Return the result, re-raising the exception if one was set."""
        if self._exception is not None:
            raise self._exception
        return self._result

    def resolve(self, result):
        """Complete the future successfully and fire its callbacks."""
        self._result = result
        for callback in self._callbacks:
            callback(self)

    def fail(self, exception):
        """Complete the future with an error and fire its callbacks."""
        self._exception = exception
        for callback in self._callbacks:
            callback(self)


class _FakeClient:
    """Stub of an rclpy service client."""

    def __init__(self, ready=True):
        """Record readiness and prepare a future to hand out."""
        self.ready = ready
        self.requests = []
        self.future = _FakeFuture()

    def service_is_ready(self):
        """Return whether the (fake) service server has been matched."""
        return self.ready

    def call_async(self, request):
        """Record the request and return the pre-built future."""
        self.requests.append(request)
        return self.future


class _FakeLogger:
    """Stub logger capturing the warnings emitted by the manager."""

    def __init__(self):
        """Start with an empty list of warnings."""
        self.warnings = []

    def warn(self, message):
        """Record a warning message."""
        self.warnings.append(message)


class _FakeNode:
    """Stub of an rclpy node exposing graph queries and client factories."""

    def __init__(self, services=None, ready=True):
        """Configure the advertised services and the client readiness."""
        self._services = services or []
        self._ready = ready
        self.clients = {}
        self.destroyed = []
        self.logger = _FakeLogger()

    def get_service_names_and_types(self):
        """Return the canned list of (service_name, types) tuples."""
        return self._services

    def create_client(self, srv_type, name, callback_group=None):
        """Create (and remember) a fake client for the given service."""
        client = _FakeClient(ready=self._ready)
        self.clients[name] = client
        return client

    def destroy_client(self, client):
        """Record the client destruction requested on shutdown."""
        self.destroyed.append(client)

    def get_logger(self):
        """Return the stub logger."""
        return self.logger


def _get_state_response(state_id, label):
    """Build a GetState response carrying the given primary state."""
    response = GetState.Response()
    response.current_state = State(id=state_id, label=label)
    return response


def _transitions_response(entries):
    """Build a GetAvailableTransitions response from (id, label, goal)."""
    response = GetAvailableTransitions.Response()
    response.available_transitions = [
        TransitionDescription(
            transition=Transition(id=tid, label=label),
            start_state=State(id=0, label='unknown'),
            goal_state=State(id=0, label=goal),
        )
        for tid, label, goal in entries
    ]
    return response


def _change_state_response(success):
    """Build a ChangeState response with the given outcome."""
    response = ChangeState.Response()
    response.success = success
    return response


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovers_only_lifecycle_nodes():
    """Only nodes exposing a GetState service are reported, sorted."""
    node = _FakeNode([
        ('/talker/get_state', ['lifecycle_msgs/srv/GetState']),
        ('/talker/change_state', ['lifecycle_msgs/srv/ChangeState']),
        ('/plain/get_parameters', ['rcl_interfaces/srv/GetParameters']),
        ('/listener/get_state', ['lifecycle_msgs/srv/GetState']),
    ])
    manager = LifecycleManager(node)
    assert manager.get_lifecycle_node_names() == ['/listener', '/talker']


def test_ignores_wrong_service_type():
    """A '/get_state' service of a different type is not a lifecycle node."""
    node = _FakeNode([('/fake/get_state', ['some_pkg/srv/GetState'])])
    manager = LifecycleManager(node)
    assert manager.get_lifecycle_node_names() == []


def test_handles_namespaced_nodes():
    """Namespaced lifecycle nodes keep their full name as the prefix."""
    node = _FakeNode([
        ('/robot/camera/get_state', ['lifecycle_msgs/srv/GetState']),
    ])
    manager = LifecycleManager(node)
    assert manager.get_lifecycle_node_names() == ['/robot/camera']


# ---------------------------------------------------------------------------
# async_get_state
# ---------------------------------------------------------------------------


def test_async_get_state_reports_state():
    """A resolved get_state future forwards the state id and label."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_get_state('/n', lambda *args: results.append(args))
    node.clients['/n/get_state'].future.resolve(
        _get_state_response(3, 'active'))

    assert results == [('/n', 3, 'active')]


def test_async_get_state_skips_when_service_not_ready():
    """No request is issued while the get_state service is unavailable."""
    node = _FakeNode(ready=False)
    manager = LifecycleManager(node)
    results = []

    manager.async_get_state('/n', lambda *args: results.append(args))

    assert results == []
    assert node.clients['/n/get_state'].requests == []


def test_async_get_state_deduplicates_in_flight_requests():
    """A second poll is skipped while the first one is still pending."""
    node = _FakeNode()
    manager = LifecycleManager(node)

    manager.async_get_state('/n', lambda *args: None)
    manager.async_get_state('/n', lambda *args: None)

    assert len(node.clients['/n/get_state'].requests) == 1


def test_async_get_state_allows_new_request_after_completion():
    """Once the future completes, the node can be polled again."""
    node = _FakeNode()
    manager = LifecycleManager(node)

    manager.async_get_state('/n', lambda *args: None)
    node.clients['/n/get_state'].future.resolve(
        _get_state_response(1, 'unconfigured'))
    manager.async_get_state('/n', lambda *args: None)

    assert len(node.clients['/n/get_state'].requests) == 2


def test_async_get_state_logs_service_failure():
    """A failed get_state call is logged and reports nothing."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_get_state('/n', lambda *args: results.append(args))
    node.clients['/n/get_state'].future.fail(RuntimeError('boom'))

    assert results == []
    assert any('get_state failed' in w for w in node.logger.warnings)


# ---------------------------------------------------------------------------
# async_get_available_transitions
# ---------------------------------------------------------------------------


def test_async_get_transitions_reports_tuples():
    """Available transitions are flattened into (id, label, goal) tuples."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_get_available_transitions(
        '/n', lambda name, items: results.append((name, items)))
    node.clients['/n/get_available_transitions'].future.resolve(
        _transitions_response([(1, 'configure', 'configuring')]))

    assert results == [('/n', [(1, 'configure', 'configuring')])]


def test_async_get_transitions_skips_when_service_not_ready():
    """No request is issued while the transitions service is unavailable."""
    node = _FakeNode(ready=False)
    manager = LifecycleManager(node)
    results = []

    manager.async_get_available_transitions(
        '/n', lambda *args: results.append(args))

    assert results == []
    assert node.clients['/n/get_available_transitions'].requests == []


def test_async_get_transitions_deduplicates_in_flight_requests():
    """A second transitions poll is skipped while one is pending."""
    node = _FakeNode()
    manager = LifecycleManager(node)

    manager.async_get_available_transitions('/n', lambda *args: None)
    manager.async_get_available_transitions('/n', lambda *args: None)

    client = node.clients['/n/get_available_transitions']
    assert len(client.requests) == 1


def test_async_get_transitions_logs_service_failure():
    """A failed transitions call is logged and reports nothing."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_get_available_transitions(
        '/n', lambda *args: results.append(args))
    node.clients['/n/get_available_transitions'].future.fail(
        RuntimeError('boom'))

    assert results == []
    assert any(
        'get_available_transitions failed' in w
        for w in node.logger.warnings)


# ---------------------------------------------------------------------------
# async_change_state
# ---------------------------------------------------------------------------


def test_async_change_state_sends_transition_id():
    """The requested transition id is placed in the ChangeState request."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_change_state('/n', 4, lambda *args: results.append(args))
    client = node.clients['/n/change_state']
    client.future.resolve(_change_state_response(True))

    assert client.requests[0].transition.id == 4
    assert results == [('/n', True, '')]


def test_async_change_state_reports_failure_outcome():
    """An unsuccessful transition is reported as success=False."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_change_state('/n', 4, lambda *args: results.append(args))
    node.clients['/n/change_state'].future.resolve(
        _change_state_response(False))

    assert results == [('/n', False, '')]


def test_async_change_state_reports_unavailable_service():
    """When the service is missing the caller is told immediately."""
    node = _FakeNode(ready=False)
    manager = LifecycleManager(node)
    results = []

    manager.async_change_state('/n', 1, lambda *args: results.append(args))

    assert len(results) == 1
    name, success, message = results[0]
    assert (name, success) == ('/n', False)
    assert 'not available' in message


def test_async_change_state_reports_exception_message():
    """A raised service error is forwarded as the failure message."""
    node = _FakeNode()
    manager = LifecycleManager(node)
    results = []

    manager.async_change_state('/n', 1, lambda *args: results.append(args))
    node.clients['/n/change_state'].future.fail(RuntimeError('boom'))

    assert results == [('/n', False, 'boom')]


# ---------------------------------------------------------------------------
# Client caching and shutdown
# ---------------------------------------------------------------------------


def test_clients_are_created_once_per_node():
    """The service client is cached and reused across calls."""
    node = _FakeNode()
    manager = LifecycleManager(node)

    manager.async_get_state('/n', lambda *args: None)
    first = node.clients['/n/get_state']
    first.future.resolve(_get_state_response(2, 'inactive'))
    manager.async_get_state('/n', lambda *args: None)

    assert node.clients['/n/get_state'] is first


def test_shutdown_destroys_every_client():
    """Shutdown destroys the cached clients and clears the caches."""
    node = _FakeNode()
    manager = LifecycleManager(node)

    manager.async_get_state('/n', lambda *args: None)
    manager.async_get_available_transitions('/n', lambda *args: None)
    manager.async_change_state('/n', 1, lambda *args: None)

    manager.shutdown()

    assert len(node.destroyed) == 3
    # A later poll must create a brand new client rather than reuse a dead one.
    manager.async_get_state('/n', lambda *args: None)
    assert node.clients['/n/get_state'] not in node.destroyed


@pytest.mark.parametrize('suffix', [
    '/get_state',
    '/get_available_transitions',
    '/change_state',
])
def test_client_targets_the_expected_service_name(suffix):
    """Each request targets '<node><suffix>' on the managed node."""
    node = _FakeNode()
    manager = LifecycleManager(node)

    manager.async_get_state('/n', lambda *args: None)
    manager.async_get_available_transitions('/n', lambda *args: None)
    manager.async_change_state('/n', 1, lambda *args: None)

    assert f'/n{suffix}' in node.clients
