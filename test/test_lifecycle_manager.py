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
Unit tests for the LifecycleManager discovery logic.

These tests exercise the pure graph-parsing behavior with a stub node, so they
run headless and do not require a live ROS 2 graph or a display server.
"""

from rqt_lifecycle_manager.lifecycle_manager import LifecycleManager


class _FakeNode:
    """Minimal stand-in for an rclpy node exposing service discovery."""

    def __init__(self, services):
        """Store the service list returned by the discovery method."""
        self._services = services

    def get_service_names_and_types(self):
        """Return the canned list of (service_name, types) tuples."""
        return self._services


def test_discovers_only_lifecycle_nodes():
    """Only nodes exposing a GetState service are reported, sorted."""
    services = [
        ('/talker/get_state', ['lifecycle_msgs/srv/GetState']),
        ('/talker/change_state', ['lifecycle_msgs/srv/ChangeState']),
        ('/plain/get_parameters', ['rcl_interfaces/srv/GetParameters']),
        ('/listener/get_state', ['lifecycle_msgs/srv/GetState']),
    ]
    manager = LifecycleManager(_FakeNode(services))
    assert manager.get_lifecycle_node_names() == ['/listener', '/talker']


def test_ignores_wrong_service_type():
    """A '/get_state' service of a different type is not a lifecycle node."""
    services = [
        ('/fake/get_state', ['some_pkg/srv/GetState']),
    ]
    manager = LifecycleManager(_FakeNode(services))
    assert manager.get_lifecycle_node_names() == []


def test_handles_namespaced_nodes():
    """Namespaced lifecycle nodes keep their full name as the prefix."""
    services = [
        ('/robot/camera/get_state', ['lifecycle_msgs/srv/GetState']),
    ]
    manager = LifecycleManager(_FakeNode(services))
    assert manager.get_lifecycle_node_names() == ['/robot/camera']
