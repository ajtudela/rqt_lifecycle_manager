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
Unit tests for the LifecycleManagerPlugin rqt entry class.

The plugin is exercised against a stub plugin context, which stands in for the
one rqt would normally provide (exposing the shared ROS 2 node, the instance
serial number and the widget container).
"""

import pytest
from python_qt_binding.QtCore import QObject
from rqt_lifecycle_manager.lifecycle_manager_plugin import (
    LifecycleManagerPlugin,
)


class _FakeNode:
    """Minimal node stub reporting an empty ROS 2 graph."""

    def get_service_names_and_types(self):
        """Report an empty ROS 2 graph."""
        return []


class _FakeContext(QObject):
    """
    Stub of the rqt plugin context.

    It derives from ``QObject`` because the rqt ``Plugin`` base class passes
    the context straight to ``QObject.__init__`` as the parent object.
    """

    def __init__(self, serial=1):
        """Expose a stub node and record the widgets added by the plugin."""
        super().__init__()
        self.node = _FakeNode()
        self.widgets = []
        self._serial = serial

    def serial_number(self):
        """Return the instance serial number assigned by rqt."""
        return self._serial

    def add_widget(self, widget):
        """Record the widget the plugin handed over to rqt."""
        self.widgets.append(widget)


class _FakeSettings:
    """Stub of the rqt settings object backing save/restore."""

    def __init__(self, values=None):
        """Start from an optional dictionary of stored values."""
        self.values = dict(values or {})

    def set_value(self, key, value):
        """Store a value."""
        self.values[key] = value

    def value(self, key, default=None):
        """Read a value, falling back to the given default."""
        return self.values.get(key, default)


@pytest.fixture
def plugin(qapp):
    """Build the plugin on a stub context and shut it down afterwards."""
    context = _FakeContext()
    instance = LifecycleManagerPlugin(context)
    yield instance, context
    instance.shutdown_plugin()


def test_plugin_registers_its_widget(plugin):
    """The plugin hands its widget over to the rqt container."""
    instance, context = plugin

    assert context.widgets == [instance._widget]


def test_first_instance_keeps_the_plain_title(plugin):
    """A single instance keeps the unsuffixed window title."""
    instance, _ = plugin

    assert instance._widget.windowTitle() == 'Lifecycle Manager'


def test_further_instances_are_numbered(qapp):
    """Additional instances get their serial number in the title."""
    context = _FakeContext(serial=2)

    instance = LifecycleManagerPlugin(context)

    assert instance._widget.windowTitle() == 'Lifecycle Manager (2)'
    instance.shutdown_plugin()


def test_shutdown_plugin_stops_the_widget(qapp):
    """Closing the plugin stops the widget's refresh timer."""
    instance = LifecycleManagerPlugin(_FakeContext())

    instance.shutdown_plugin()

    assert not instance._widget._refresh_timer.isActive()


def test_save_settings_persists_auto_refresh(plugin):
    """The auto-refresh preference is written to the instance settings."""
    instance, _ = plugin
    instance._widget.set_auto_refresh_enabled(False)
    settings = _FakeSettings()

    instance.save_settings(_FakeSettings(), settings)

    assert settings.values['auto_refresh'] is False


@pytest.mark.parametrize('stored, expected', [
    (True, True),
    ('true', True),
    ('True', True),
    (1, True),
    ('1', True),
    (False, False),
    ('false', False),
])
def test_restore_settings_normalizes_auto_refresh(plugin, stored, expected):
    """Stored booleans may come back as strings, so they are normalized."""
    instance, _ = plugin
    settings = _FakeSettings({'auto_refresh': stored})

    instance.restore_settings(_FakeSettings(), settings)

    assert instance._widget.is_auto_refresh_enabled() is expected


def test_restore_settings_defaults_to_enabled(plugin):
    """With nothing stored, auto-refresh stays enabled."""
    instance, _ = plugin
    instance._widget.set_auto_refresh_enabled(False)

    instance.restore_settings(_FakeSettings(), _FakeSettings())

    assert instance._widget.is_auto_refresh_enabled() is True
