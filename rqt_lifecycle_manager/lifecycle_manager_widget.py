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

The widget lists every lifecycle node, shows the current state of the selected
node and offers a button per available transition. Results coming from ROS 2
arrive on the executor thread and are delivered to this GUI thread through Qt
signals, which keeps the interface fully responsive at all times.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from python_qt_binding.QtCore import Qt, QTimer, Signal
from python_qt_binding.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
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

# How often, in milliseconds, the selected node is polled for state changes.
_REFRESH_INTERVAL_MS = 1000


class LifecycleManagerWidget(QWidget):
    """
    Interactive view to inspect and control ROS 2 lifecycle nodes.

    Parameters
    ----------
    node : rclpy.node.Node
        The ROS 2 node (spun by ``rqt_gui_py``) used to talk to the graph.

    """

    # Signals used to hand ROS 2 results back to the Qt GUI thread. Emitting a
    # signal from the executor thread is delivered here as a queued connection.
    state_received = Signal(str, int, str)
    transitions_received = Signal(str, list)
    change_state_result = Signal(str, bool, str)

    def __init__(self, node) -> None:
        """
        Build the widget and start the non-blocking refresh timer.

        Parameters
        ----------
        node : rclpy.node.Node
            The ROS 2 node used to create the lifecycle manager backend.

        """
        super().__init__()
        self.setObjectName('LifecycleManagerWidget')
        self.setWindowTitle('Lifecycle Manager')

        self._manager = LifecycleManager(node)
        self._selected_node: Optional[str] = None
        self._known_nodes: List[str] = []
        # Cache of the transitions currently shown, to avoid needless rebuilds.
        self._displayed_transitions: Optional[
            List[Tuple[int, str, str]]] = None

        self._build_ui()

        # Deliver ROS results to the GUI thread (queued across threads).
        self.state_received.connect(self._update_state)
        self.transitions_received.connect(self._update_transitions)
        self.change_state_result.connect(self._on_change_state_result)

        # Periodic, non-blocking refresh running on the GUI thread.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(_REFRESH_INTERVAL_MS)

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

        controls = QHBoxLayout()
        controls.addWidget(self._refresh_button)
        controls.addWidget(self._auto_refresh)
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
        """Refresh the node list and re-poll the selected node."""
        self._refresh_nodes()
        self._poll_selected()

    def _refresh_nodes(self) -> None:
        """Rebuild the node list widget only when the set of nodes changes."""
        names = self._manager.get_lifecycle_node_names()
        if names == self._known_nodes:
            return
        self._known_nodes = names

        selected = self._selected_node
        # Block signals so the programmatic rebuild does not fire callbacks.
        self._node_list.blockSignals(True)
        self._node_list.clear()
        for name in names:
            self._node_list.addItem(QListWidgetItem(name))
        if selected in names:
            items = self._node_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            if items:
                self._node_list.setCurrentItem(items[0])
        self._node_list.blockSignals(False)

        # The previously selected node disappeared from the graph.
        if selected is not None and selected not in names:
            self._selected_node = None
            self._clear_details()

    def _poll_selected(self) -> None:
        """Asynchronously request the state and transitions of the node."""
        if self._selected_node is None:
            return
        self._manager.async_get_state(
            self._selected_node, self.state_received.emit)
        self._manager.async_get_available_transitions(
            self._selected_node, self.transitions_received.emit)

    # -------------------------------------------------------------------------
    # User interactions (GUI thread)
    # -------------------------------------------------------------------------

    def _on_node_selected(self) -> None:
        """Handle a change in the selected lifecycle node."""
        items = self._node_list.selectedItems()
        if not items:
            return
        self._selected_node = items[0].text()
        self._node_label.setText(self._selected_node)
        self._status_label.setText('')
        # Force a rebuild for the newly selected node.
        self._displayed_transitions = None
        self._poll_selected()

    def _on_auto_refresh_toggled(self, enabled: bool) -> None:
        """Start or stop the periodic refresh timer."""
        if enabled:
            self._refresh_timer.start(_REFRESH_INTERVAL_MS)
        else:
            self._refresh_timer.stop()

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
        """Display the reported state of a node if it is still selected."""
        if node_name != self._selected_node:
            return
        text = state_label.upper() if state_label else 'UNKNOWN'
        color = _STATE_COLORS.get(state_id, _TRANSITION_STATE_COLOR)
        self._state_label.setText(text)
        self._state_label.setStyleSheet(
            f'background-color: {color}; color: white; font-weight: bold; '
            f'padding: 6px; border-radius: 4px;')

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

    def _reset_state_style(self) -> None:
        """Restore the neutral style of the state label."""
        self._state_label.setStyleSheet(
            'background-color: #eceff1; color: #37474f; font-weight: bold; '
            'padding: 6px; border-radius: 4px;')

    def _clear_details(self) -> None:
        """Reset the details panel when no node is selected."""
        self._node_label.setText('No node selected')
        self._state_label.setText('—')
        self._reset_state_style()
        self._clear_transitions()
        self._displayed_transitions = None
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

    def shutdown(self) -> None:
        """Stop the timer and release all ROS 2 resources."""
        self._refresh_timer.stop()
        self._manager.shutdown()
