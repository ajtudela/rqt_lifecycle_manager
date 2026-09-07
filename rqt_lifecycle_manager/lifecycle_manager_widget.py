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
Qt widget for the rqt Lifecycle Manager plugin.

The widget lists every lifecycle node, color-coding each row with its current
state as a lightweight dashboard, shows the full state of the selected node
and offers a button per available transition. Results coming from ROS 2
arrive on the executor thread and are delivered to this GUI thread through Qt
signals, which keeps the interface fully responsive at all times.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from python_qt_binding.QtCore import Qt, QTimer, Signal
from python_qt_binding.QtGui import QColor, QIcon, QPalette, QPixmap
from python_qt_binding.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from rqt_lifecycle_manager.lifecycle_manager import LifecycleManager

# Background colors for each primary lifecycle state id (lifecycle_msgs/State).
_STATE_COLORS = {
    0: '#9e9e9e',   # unknown
    1: '#607d8b',   # unconfigured
    2: '#fb8c00',   # inactive
    3: '#43a047',   # active
    4: '#e53935',   # finalized
}
# Fallback color used while the node is in a transition state (ids 10-15).
_TRANSITION_STATE_COLOR = '#29b6f6'

# Final resting state reached by each primary transition. This is clearer than
# the intermediate state that get_available_transitions reports as the goal
# (e.g. 'deactivating' instead of 'inactive').
_TRANSITION_GOAL_LABELS = {
    'configure': 'inactive',
    'cleanup': 'unconfigured',
    'activate': 'active',
    'deactivate': 'inactive',
    'shutdown': 'finalized',
}

# Default, minimum, maximum and step (all in ms) for the refresh interval
# the user can pick from the GUI.
_DEFAULT_REFRESH_INTERVAL_MS = 1000
_MIN_REFRESH_INTERVAL_MS = 200
_MAX_REFRESH_INTERVAL_MS = 10000
_REFRESH_INTERVAL_STEP_MS = 100

# Side, in pixels, of the solid-color square icon used to show each node's
# state directly in the node list (the "dashboard" view).
_DASHBOARD_ICON_SIZE = 12


class LifecycleManagerWidget(QWidget):
    """
    Interactive view to inspect and control ROS 2 lifecycle nodes.

    Parameters
    ----------
    node : rclpy.node.Node
        The ROS 2 node (spun by ``rqt_gui_py``) used to talk to the graph.
    manager : LifecycleManager, optional
        Backend to use instead of building a fresh ``LifecycleManager(node)``.
        Mainly intended for tests, which can inject a stub instead of
        monkey-patching the private ``_manager`` attribute after
        construction.

    """

    # Signals used to hand ROS 2 results back to the Qt GUI thread. Emitting a
    # signal from the executor thread is delivered here as a queued connection.
    state_received = Signal(str, int, str)
    transitions_received = Signal(str, list)
    change_state_result = Signal(str, bool, str)

    def __init__(self, node, manager: Optional[LifecycleManager] = None) -> None:
        """
        Build the widget and start the non-blocking refresh timer.

        Parameters
        ----------
        node : rclpy.node.Node
            The ROS 2 node used to create the lifecycle manager backend,
            when ``manager`` is not provided.
        manager : LifecycleManager, optional
            Backend to use instead of building a fresh
            ``LifecycleManager(node)``.

        """
        super().__init__()
        self.setObjectName('LifecycleManagerWidget')
        self.setWindowTitle('Lifecycle Manager')

        self._manager = manager if manager is not None else LifecycleManager(node)
        self._selected_node: Optional[str] = None
        self._known_nodes: List[str] = []
        # Last known state id of every currently discovered node, used to
        # color-code the node list as a lightweight dashboard.
        self._node_states: Dict[str, int] = {}
        # Cache of the transitions currently shown, to avoid needless rebuilds.
        self._displayed_transitions: Optional[
            List[Tuple[int, str, str]]] = None
        # Last state id seen for the selected node, used to re-query the
        # available transitions only when the state actually changes.
        self._last_state_id: Optional[int] = None

        self._build_ui()

        # Deliver ROS results to the GUI thread (queued across threads).
        self.state_received.connect(self._update_state)
        self.transitions_received.connect(self._update_transitions)
        self.change_state_result.connect(self._on_change_state_result)

        # Periodic, non-blocking refresh running on the GUI thread.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(self._interval_spinbox.value())

        self._refresh()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create and lay out every widget of the plugin."""
        # Left panel: list of lifecycle nodes plus controls.
        self._node_list = QListWidget()
        self._node_list.itemSelectionChanged.connect(self._on_node_selected)

        self._refresh_button = QPushButton('Refresh')
        self._refresh_button.clicked.connect(self._refresh)

        self._auto_refresh = QCheckBox('Auto-refresh')
        self._auto_refresh.setChecked(True)
        self._auto_refresh.toggled.connect(self._on_auto_refresh_toggled)

        self._interval_spinbox = QSpinBox()
        self._interval_spinbox.setRange(
            _MIN_REFRESH_INTERVAL_MS, _MAX_REFRESH_INTERVAL_MS)
        self._interval_spinbox.setSingleStep(_REFRESH_INTERVAL_STEP_MS)
        self._interval_spinbox.setValue(_DEFAULT_REFRESH_INTERVAL_MS)
        self._interval_spinbox.setSuffix(' ms')
        self._interval_spinbox.valueChanged.connect(
            self._on_refresh_interval_changed)

        controls = QHBoxLayout()
        controls.addWidget(self._refresh_button)
        controls.addWidget(self._auto_refresh)
        controls.addWidget(QLabel('Interval:'))
        controls.addWidget(self._interval_spinbox)
        controls.addStretch(1)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel('Lifecycle nodes:'))
        left_layout.addWidget(self._node_list)
        left_layout.addLayout(controls)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Right panel: selected node details and transition controls.
        self._node_label = QLabel('No node selected')
        self._node_label.setStyleSheet('font-weight: bold; font-size: 14px;')

        self._state_label = QLabel('—')
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_label.setMinimumHeight(36)
        self._reset_state_style()

        self._transitions_box = QGroupBox('Available transitions')
        self._transitions_layout = QVBoxLayout()
        self._transitions_box.setLayout(self._transitions_layout)

        self._status_label = QLabel('')
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet('color: gray;')

        right_layout = QVBoxLayout()
        right_layout.addWidget(self._node_label)
        right_layout.addWidget(QLabel('Current state:'))
        right_layout.addWidget(self._state_label)
        right_layout.addWidget(self._transitions_box)
        right_layout.addStretch(1)
        right_layout.addWidget(self._status_label)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout = QHBoxLayout()
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    # -------------------------------------------------------------------------
    # Refresh cycle (GUI thread)
    # -------------------------------------------------------------------------

    def _refresh(self) -> None:
        """
        Refresh the discovered node list.

        The selected node's state is not re-polled here: it is queried once
        when selected and kept current afterwards by the push-based
        ``transition_event`` subscription every discovered node gets in
        ``_refresh_nodes``.
        """
        self._refresh_nodes()

    def _refresh_nodes(self) -> None:
        """
        Rebuild the node list widget only when the set of nodes changes.

        Every newly discovered node gets an initial state read plus a
        standing ``transition_event`` subscription, so the list can show
        each node's state at a glance (like a small dashboard) without
        polling all of them on every cycle. Nodes that leave the graph have
        their resources released and their cached state dropped.
        """
        names = self._manager.get_lifecycle_node_names()
        if names == self._known_nodes:
            return
        previous_names = self._known_nodes
        self._known_nodes = names

        for name in set(names) - set(previous_names):
            self._manager.async_get_state(name, self.state_received.emit)
            self._manager.subscribe_to_transitions(
                name, self.state_received.emit)
        for name in set(previous_names) - set(names):
            self._manager.release_node(name)
            self._node_states.pop(name, None)

        selected = self._selected_node
        # Block signals so the programmatic rebuild does not fire callbacks.
        self._node_list.blockSignals(True)
        self._node_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            if name in self._node_states:
                item.setIcon(self._state_icon(self._node_states[name]))
            self._node_list.addItem(item)
        if selected in names:
            items = self._node_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            if items:
                self._node_list.setCurrentItem(items[0])
        self._node_list.blockSignals(False)

        # The previously selected node disappeared from the graph (its
        # resources were already released above): just reset the panel.
        if selected is not None and selected not in names:
            self._selected_node = None
            self._clear_details()

    def _poll_selected(self) -> None:
        """
        Asynchronously request a one-off state read of the selected node.

        Used right after selecting a node (to get an initial reading before
        the first ``transition_event`` arrives) and right after requesting a
        transition. The available transitions are a deterministic function
        of the current state, so they are only re-queried from
        ``_update_state`` when the reported ``state_id`` actually changes.
        """
        if self._selected_node is None:
            return
        self._manager.async_get_state(
            self._selected_node, self.state_received.emit)

    # -------------------------------------------------------------------------
    # User interactions (GUI thread)
    # -------------------------------------------------------------------------

    def _on_node_selected(self) -> None:
        """
        Handle a change in the selected lifecycle node.

        The node is already subscribed to push-based updates (every
        discovered node is, for the dashboard) and switching away from it
        does not release that subscription, since its row still needs to
        stay current. Only a one-off read is issued here to populate the
        detail panel immediately, without waiting for the next event.
        """
        items = self._node_list.selectedItems()
        if not items:
            return
        self._selected_node = items[0].text()
        self._node_label.setText(self._selected_node)
        self._status_label.setText('')
        # Force a rebuild and a fresh transitions query for the new node.
        self._displayed_transitions = None
        self._last_state_id = None
        self._poll_selected()

    def _on_auto_refresh_toggled(self, enabled: bool) -> None:
        """Start or stop the periodic refresh timer."""
        if enabled:
            self._refresh_timer.start(self._interval_spinbox.value())
        else:
            self._refresh_timer.stop()

    def _on_refresh_interval_changed(self, interval_ms: int) -> None:
        """Apply a new polling interval to the running timer, if active."""
        if self._refresh_timer.isActive():
            self._refresh_timer.start(interval_ms)

    def _request_transition(self, transition_id: int, label: str) -> None:
        """Trigger the given transition on the selected node."""
        if self._selected_node is None:
            return
        self._status_label.setText(f'Requesting transition "{label}"…')
        self._set_transitions_enabled(False)
        self._manager.async_change_state(
            self._selected_node, transition_id, self.change_state_result.emit)

    # -------------------------------------------------------------------------
    # ROS result slots (GUI thread, invoked via queued signals)
    # -------------------------------------------------------------------------

    def _update_state(
        self, node_name: str, state_id: int, state_label: str
    ) -> None:
        """
        Record the reported state and refresh the panel if still selected.

        Every discovered node's state is cached and reflected as a small
        icon next to its name in the list, regardless of selection; the
        detail panel below is only updated for the currently selected node.
        """
        self._node_states[node_name] = state_id
        self._apply_node_item_icon(node_name, state_id)
        if node_name != self._selected_node:
            return
        text = state_label.upper() if state_label else 'UNKNOWN'
        color = _STATE_COLORS.get(state_id, _TRANSITION_STATE_COLOR)
        self._state_label.setText(text)
        self._state_label.setStyleSheet(
            f'background-color: {color}; color: white; font-weight: bold; '
            f'padding: 6px; border-radius: 4px;')
        # The available transitions only change together with the state, so
        # they are re-queried here instead of on every polling cycle.
        if state_id != self._last_state_id:
            self._last_state_id = state_id
            self._manager.async_get_available_transitions(
                node_name, self.transitions_received.emit)

    def _update_transitions(
        self, node_name: str, transitions: List[Tuple[int, str, str]]
    ) -> None:
        """Rebuild the transition buttons for the selected node."""
        if node_name != self._selected_node:
            return
        # Skip the rebuild when the available transitions are unchanged.
        if transitions == self._displayed_transitions:
            return
        self._displayed_transitions = transitions
        self._clear_transitions()
        if not transitions:
            self._transitions_layout.addWidget(
                QLabel('No transitions available from this state.'))
            return
        for transition_id, label, goal_label in transitions:
            goal = _TRANSITION_GOAL_LABELS.get(label, goal_label)
            text = f'{label}  →  {goal}' if goal else label
            button = QPushButton(text)
            # Bind the current values so every button keeps its own target.
            button.clicked.connect(
                lambda checked=False, tid=transition_id, lbl=label:
                self._request_transition(tid, lbl))
            self._transitions_layout.addWidget(button)

    def _on_change_state_result(
        self, node_name: str, success: bool, message: str
    ) -> None:
        """Report the outcome of a transition and re-poll the node."""
        if node_name != self._selected_node:
            return
        if success:
            self._status_label.setText('Transition succeeded.')
        else:
            text = 'Transition failed.'
            if message:
                text += f' ({message})'
            self._status_label.setText(text)
        # Re-enable the buttons even if the state (and thus the transitions)
        # did not change, then refresh to reflect any new state.
        self._set_transitions_enabled(True)
        self._poll_selected()

    # -------------------------------------------------------------------------
    # Small view helpers
    # -------------------------------------------------------------------------

    def _clear_transitions(self) -> None:
        """Remove every widget currently inside the transitions box."""
        while self._transitions_layout.count():
            item = self._transitions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _set_transitions_enabled(self, enabled: bool) -> None:
        """Enable or disable every transition button at once."""
        for index in range(self._transitions_layout.count()):
            widget = self._transitions_layout.itemAt(index).widget()
            if isinstance(widget, QPushButton):
                widget.setEnabled(enabled)

    def _apply_node_item_icon(self, node_name: str, state_id: int) -> None:
        """Color-code a node's row in the list to show its state at a glance."""
        items = self._node_list.findItems(node_name, Qt.MatchFlag.MatchExactly)
        if items:
            items[0].setIcon(self._state_icon(state_id))

    @staticmethod
    def _state_icon(state_id: int) -> QIcon:
        """Build a small solid-color icon representing a lifecycle state."""
        color = QColor(_STATE_COLORS.get(state_id, _TRANSITION_STATE_COLOR))
        pixmap = QPixmap(_DASHBOARD_ICON_SIZE, _DASHBOARD_ICON_SIZE)
        pixmap.fill(color)
        return QIcon(pixmap)

    def _reset_state_style(self) -> None:
        """
        Restore the neutral style of the state label.

        The neutral colors are derived from the active Qt palette (instead
        of being hardcoded for a light theme), so the label stays legible
        under a dark rqt theme too. The semantic state colors in
        ``_STATE_COLORS`` are kept as-is since they carry meaning.
        """
        palette = self.palette()
        background = palette.color(QPalette.ColorRole.Window).name()
        foreground = palette.color(QPalette.ColorRole.WindowText).name()
        self._state_label.setStyleSheet(
            f'background-color: {background}; color: {foreground}; '
            f'font-weight: bold; padding: 6px; border-radius: 4px;')

    def _clear_details(self) -> None:
        """Reset the details panel when no node is selected."""
        self._node_label.setText('No node selected')
        self._state_label.setText('—')
        self._reset_state_style()
        self._clear_transitions()
        self._displayed_transitions = None
        self._last_state_id = None
        self._status_label.setText('')

    # -------------------------------------------------------------------------
    # Settings and shutdown (used by the plugin)
    # -------------------------------------------------------------------------

    def is_auto_refresh_enabled(self) -> bool:
        """Return whether the periodic refresh is currently enabled."""
        return self._auto_refresh.isChecked()

    def set_auto_refresh_enabled(self, enabled: bool) -> None:
        """Enable or disable the periodic refresh (restores saved value)."""
        self._auto_refresh.setChecked(enabled)

    def refresh_interval_ms(self) -> int:
        """Return the currently configured polling interval, in ms."""
        return self._interval_spinbox.value()

    def set_refresh_interval_ms(self, interval_ms: int) -> None:
        """Restore a previously saved polling interval, in ms."""
        self._interval_spinbox.setValue(interval_ms)

    def shutdown(self) -> None:
        """Stop the timer and release all ROS 2 resources."""
        self._refresh_timer.stop()
        self._manager.shutdown()
