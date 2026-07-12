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
Unit tests for the LifecycleManagerWidget.

The widget is driven headlessly (Qt ``offscreen`` platform, selected in
``conftest.py``) against a stub manager, so the tests assert on the view logic
without needing a display server or a live ROS 2 graph.
"""

import pytest
from python_qt_binding.QtWidgets import QLabel, QPushButton
from rqt_lifecycle_manager.lifecycle_manager_widget import (
    LifecycleManagerWidget,
)


class _FakeManager:
    """Stub of LifecycleManager recording the requests made by the widget."""

    def __init__(self, names=None):
        """Configure the discovered node names and clear the call records."""
        self.names = list(names or [])
        self.state_requests = []
        self.transition_requests = []
        self.change_requests = []
        self.shutdown_called = False

    def get_lifecycle_node_names(self):
        """Return the configured list of lifecycle node names."""
        return list(self.names)

    def async_get_state(self, node_name, on_result):
        """Record a state poll."""
        self.state_requests.append((node_name, on_result))

    def async_get_available_transitions(self, node_name, on_result):
        """Record a transitions poll."""
        self.transition_requests.append((node_name, on_result))

    def async_change_state(self, node_name, transition_id, on_result):
        """Record a transition request."""
        self.change_requests.append((node_name, transition_id, on_result))

    def shutdown(self):
        """Record that the widget released the backend."""
        self.shutdown_called = True


class _FakeNode:
    """Minimal node stub; the real manager is swapped out after building."""

    def get_service_names_and_types(self):
        """Report an empty ROS 2 graph."""
        return []


@pytest.fixture
def widget(qapp):
    """Build a widget backed by a stub manager and tear it down after use."""
    view = LifecycleManagerWidget(_FakeNode())
    manager = _FakeManager()
    # Replace the real backend so the tests observe the requests it receives.
    view._manager = manager
    yield view, manager
    view.shutdown()


def _transition_buttons(view):
    """Return the transition buttons currently shown in the widget."""
    layout = view._transitions_layout
    return [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), QPushButton)
    ]


def _select_first_node(view):
    """Select the first entry of the node list, as a user click would."""
    view._node_list.setCurrentRow(0)


# ---------------------------------------------------------------------------
# Node list
# ---------------------------------------------------------------------------


def test_node_list_shows_discovered_nodes(widget):
    """Discovered lifecycle nodes are listed in the widget."""
    view, manager = widget
    manager.names = ['/a', '/b']

    view._refresh()

    labels = [view._node_list.item(i).text()
              for i in range(view._node_list.count())]
    assert labels == ['/a', '/b']


def test_node_list_is_not_rebuilt_when_unchanged(widget):
    """An unchanged node set leaves the existing list items untouched."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    first_item = view._node_list.item(0)

    view._refresh()

    assert view._node_list.item(0) is first_item


def test_selecting_a_node_polls_state_and_transitions(widget):
    """Selecting a node shows its name and polls state plus transitions."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()

    _select_first_node(view)

    assert view._selected_node == '/a'
    assert view._node_label.text() == '/a'
    assert manager.state_requests[-1][0] == '/a'
    assert manager.transition_requests[-1][0] == '/a'


def test_vanished_node_clears_the_details_panel(widget):
    """When the selected node leaves the graph the details are reset."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    manager.names = []
    view._refresh()

    assert view._selected_node is None
    assert view._node_label.text() == 'No node selected'
    assert _transition_buttons(view) == []


def test_polling_without_selection_makes_no_request(widget):
    """With no node selected the widget issues no service calls."""
    view, manager = widget

    view._refresh()

    assert manager.state_requests == []
    assert manager.transition_requests == []


def test_selection_survives_a_node_list_rebuild(widget):
    """A node still on the graph stays selected when the list is rebuilt."""
    view, manager = widget
    manager.names = ['/b']
    view._refresh()
    _select_first_node(view)

    # A new node appears, which forces the list widget to be rebuilt.
    manager.names = ['/a', '/b']
    view._refresh()

    assert view._selected_node == '/b'
    assert view._node_list.currentItem().text() == '/b'


def test_empty_selection_is_ignored(widget):
    """Clearing the selection does not change the currently shown node."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._node_list.clearSelection()
    view._on_node_selected()

    assert view._selected_node == '/a'


# ---------------------------------------------------------------------------
# State display
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('state_id, label, colour', [
    (1, 'unconfigured', '#607d8b'),
    (2, 'inactive', '#fb8c00'),
    (3, 'active', '#43a047'),
    (4, 'finalized', '#e53935'),
    (13, 'activating', '#29b6f6'),
])
def test_state_is_shown_with_its_colour(widget, state_id, label, colour):
    """Each lifecycle state is rendered upper-case with its own colour."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._update_state('/a', state_id, label)

    assert view._state_label.text() == label.upper()
    assert colour in view._state_label.styleSheet()


def test_state_without_label_shows_unknown(widget):
    """An empty state label falls back to 'UNKNOWN'."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._update_state('/a', 0, '')

    assert view._state_label.text() == 'UNKNOWN'


def test_state_of_another_node_is_ignored(widget):
    """A late reply for a different node does not overwrite the view."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)
    view._update_state('/a', 3, 'active')

    view._update_state('/other', 4, 'finalized')

    assert view._state_label.text() == 'ACTIVE'


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def test_transition_buttons_show_final_resting_state(widget):
    """Buttons show the final state, not the intermediate one from the API."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._update_transitions('/a', [(4, 'deactivate', 'deactivating')])

    texts = [button.text() for button in _transition_buttons(view)]
    assert texts == ['deactivate  →  inactive']


def test_unknown_transition_falls_back_to_api_goal(widget):
    """An unmapped transition keeps whatever goal the API reported."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._update_transitions('/a', [(99, 'custom', 'somewhere')])

    texts = [button.text() for button in _transition_buttons(view)]
    assert texts == ['custom  →  somewhere']


def test_no_transitions_shows_a_message(widget):
    """A state with no available transitions shows an explanatory label."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._update_transitions('/a', [])

    layout = view._transitions_layout
    labels = [
        layout.itemAt(i).widget().text()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), QLabel)
    ]
    assert labels == ['No transitions available from this state.']


def test_transitions_of_another_node_are_ignored(widget):
    """A late transitions reply for a different node is discarded."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._update_transitions('/other', [(1, 'configure', 'configuring')])

    assert _transition_buttons(view) == []


def test_identical_transitions_are_not_rebuilt(widget):
    """Re-reporting the same transitions keeps the existing buttons."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)
    view._update_transitions('/a', [(1, 'configure', 'configuring')])
    first_button = _transition_buttons(view)[0]

    view._update_transitions('/a', [(1, 'configure', 'configuring')])

    assert _transition_buttons(view)[0] is first_button


def test_changed_transitions_replace_the_buttons(widget):
    """New transitions discard the buttons shown for the previous state."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)
    view._update_transitions('/a', [(1, 'configure', 'configuring')])

    view._update_transitions('/a', [(3, 'activate', 'activating')])

    texts = [button.text() for button in _transition_buttons(view)]
    assert texts == ['activate  →  active']


def test_clicking_a_button_requests_that_transition(widget):
    """Pressing a transition button asks the backend to change state."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)
    view._update_transitions('/a', [(1, 'configure', 'configuring')])

    _transition_buttons(view)[0].click()

    assert manager.change_requests[-1][0] == '/a'
    assert manager.change_requests[-1][1] == 1
    # The button is disabled while the request is in flight.
    assert not _transition_buttons(view)[0].isEnabled()


def test_transition_without_selection_is_ignored(widget):
    """Requesting a transition with no node selected does nothing."""
    view, manager = widget

    view._request_transition(1, 'configure')

    assert manager.change_requests == []


# ---------------------------------------------------------------------------
# Transition results
# ---------------------------------------------------------------------------


def test_successful_transition_reports_and_repolls(widget):
    """A successful transition updates the status and re-polls the node."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)
    polls_before = len(manager.state_requests)

    view._on_change_state_result('/a', True, '')

    assert view._status_label.text() == 'Transition succeeded.'
    assert len(manager.state_requests) == polls_before + 1


def test_failed_transition_reports_the_message(widget):
    """A failed transition surfaces the error message in the status line."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._on_change_state_result('/a', False, 'boom')

    assert view._status_label.text() == 'Transition failed. (boom)'


def test_failed_transition_without_message(widget):
    """A failure with no message still reports the failure."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._on_change_state_result('/a', False, '')

    assert view._status_label.text() == 'Transition failed.'


def test_transition_result_re_enables_the_buttons(widget):
    """The buttons come back after the transition request completes."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)
    view._update_transitions('/a', [(1, 'configure', 'configuring')])
    _transition_buttons(view)[0].click()

    view._on_change_state_result('/a', False, 'boom')

    assert _transition_buttons(view)[0].isEnabled()


def test_transition_result_of_another_node_is_ignored(widget):
    """A result for a node that is no longer selected is discarded."""
    view, manager = widget
    manager.names = ['/a']
    view._refresh()
    _select_first_node(view)

    view._on_change_state_result('/other', True, '')

    assert view._status_label.text() == ''


# ---------------------------------------------------------------------------
# Auto-refresh and shutdown
# ---------------------------------------------------------------------------


def test_auto_refresh_is_enabled_by_default(widget):
    """The periodic refresh timer runs as soon as the widget is built."""
    view, _ = widget

    assert view.is_auto_refresh_enabled()
    assert view._refresh_timer.isActive()


def test_disabling_auto_refresh_stops_the_timer(widget):
    """Unchecking auto-refresh stops the periodic polling."""
    view, _ = widget

    view.set_auto_refresh_enabled(False)

    assert not view.is_auto_refresh_enabled()
    assert not view._refresh_timer.isActive()


def test_re_enabling_auto_refresh_restarts_the_timer(widget):
    """Re-checking auto-refresh restarts the periodic polling."""
    view, _ = widget
    view.set_auto_refresh_enabled(False)

    view.set_auto_refresh_enabled(True)

    assert view._refresh_timer.isActive()


def test_shutdown_stops_timer_and_releases_backend(widget):
    """Shutting the widget down stops the timer and frees ROS resources."""
    view, manager = widget

    view.shutdown()

    assert not view._refresh_timer.isActive()
    assert manager.shutdown_called
