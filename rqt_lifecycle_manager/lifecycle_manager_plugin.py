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
rqt plugin entry class for the Lifecycle Manager.

This binds the :class:`LifecycleManagerWidget` into an ``rqt_gui_py`` plugin.
The ROS 2 node is taken from the plugin context, which ``rqt_gui_py`` already
spins in a background executor thread; this is what allows the widget to issue
non-blocking asynchronous service calls.
"""

from __future__ import annotations

from rqt_gui_py.plugin import Plugin

from rqt_lifecycle_manager.lifecycle_manager_widget import (
    LifecycleManagerWidget,
)


class LifecycleManagerPlugin(Plugin):
    """
    rqt plugin that inspects and controls ROS 2 lifecycle nodes.

    Parameters
    ----------
    context : qt_gui.plugin_context.PluginContext
        The plugin context provided by rqt, exposing the shared ROS 2 node.

    """

    def __init__(self, context) -> None:
        """
        Create the widget and register it with the rqt container.

        Parameters
        ----------
        context : qt_gui.plugin_context.PluginContext
            The plugin context provided by rqt.

        """
        super().__init__(context)
        self.setObjectName('LifecycleManagerPlugin')

        self._widget = LifecycleManagerWidget(context.node)
        # Disambiguate the title when several instances are opened at once.
        if context.serial_number() > 1:
            self._widget.setWindowTitle(
                f'{self._widget.windowTitle()} ({context.serial_number()})')
        context.add_widget(self._widget)

    def shutdown_plugin(self) -> None:
        """Release timers and ROS 2 resources when the plugin closes."""
        self._widget.shutdown()

    def save_settings(self, plugin_settings, instance_settings) -> None:
        """Persist the auto-refresh preference across sessions."""
        instance_settings.set_value(
            'auto_refresh', self._widget.is_auto_refresh_enabled())

    def restore_settings(self, plugin_settings, instance_settings) -> None:
        """Restore the auto-refresh preference from a previous session."""
        value = instance_settings.value('auto_refresh', True)
        # QSettings may return the boolean as a string; normalize it.
        enabled = value in (True, 'true', 'True', 1, '1')
        self._widget.set_auto_refresh_enabled(enabled)
