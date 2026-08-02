^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package rqt_lifecycle_manager
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.2.0 (02-08-2026)
------------------

Added
-----
* Added ``LifecycleManager.subscribe_to_transitions()`` in ``lifecycle_manager.py``,
  subscribing to a node's ``<node>/transition_event`` topic
  (``lifecycle_msgs/msg/TransitionEvent``) so state changes are pushed instantly instead of
  waiting for the next polling cycle.
* Added ``LifecycleManager.release_node()`` to destroy the cached service clients and
  transition_event subscription of a single node.
* Added a color-coded dashboard icon per row in ``LifecycleManagerWidget``'s node list,
  reflecting every discovered node's last known state at a glance instead of only the
  selected one.
* Added a ``QSpinBox`` (200-10000 ms) next to the auto-refresh checkbox to make the polling
  interval configurable, persisted as ``refresh_interval_ms`` via
  ``LifecycleManagerPlugin.save_settings``/``restore_settings``.
* Added an optional ``manager`` constructor parameter to ``LifecycleManagerWidget`` so tests
  can inject a stub backend instead of monkey-patching ``_manager`` after construction.
* Added 39 new test cases (110 total, up from 71) covering all of the above plus the
  ``threading.Lock`` guarding ``LifecycleManager._pending``.

Changed
-------
* Changed ``LifecycleManagerWidget`` to query ``get_available_transitions`` only when a
  node's reported ``state_id`` changes, instead of on every polling cycle.
* Changed the periodic refresh timer to only re-scan the discovered node list; per-node state
  now arrives via the ``transition_event`` subscription established for every discovered node.
* Changed ``LifecycleManagerWidget._reset_state_style()`` to derive the neutral state colors
  from ``self.palette()`` instead of hardcoded light-theme hex values, so it follows a dark
  rqt theme too.
* Changed ``main(args=None)`` in ``main.py`` to forward ``args`` when given instead of always
  using ``sys.argv``.
* Changed ``LifecycleManager._pending`` to be guarded by a ``threading.Lock`` and documented
  the manager's threading model in its class docstring.
* Changed the README to consistently reference ROS 2 Rolling (tested-under note, rosdep
  target and docs.ros.org links), matching the CI workflow and badges.

Fixed
-----
* Fixed unbounded growth of cached service clients and subscriptions: resources are now
  released via ``LifecycleManager.release_node()`` as soon as a node leaves the graph.

0.1.0 (12-07-2026)
------------------
* Initial release.
* Added ``LifecycleManager`` backend in ``lifecycle_manager.py`` that discovers
  lifecycle nodes and performs fully asynchronous ``get_state``,
  ``get_available_transitions`` and ``change_state`` service calls.
* Added ``LifecycleManagerWidget`` in ``lifecycle_manager_widget.py`` with a
  node list, color-coded state display and dynamic per-transition buttons.
* Added ``LifecycleManagerPlugin`` in ``lifecycle_manager_plugin.py`` as the
  ``rqt_gui_py`` entry class, plus a standalone entry point in ``main.py``.
* Registered the rqt plugin through ``plugin.xml``.
* Added a test suite reaching 99% statement coverage (71 tests, all passing
  under ROS 2 Rolling):

  - ``test/test_lifecycle_manager.py`` with 21 cases covering node discovery,
    the asynchronous ``get_state`` / ``get_available_transitions`` /
    ``change_state`` paths, in-flight request de-duplication, service-failure
    handling, client caching and ``shutdown()``.
  - ``test/test_lifecycle_manager_widget.py`` with 31 cases driving the view
    headlessly: node listing, selection, color-coded states, transition
    buttons, transition results and the auto-refresh timer.
  - ``test/test_lifecycle_manager_plugin.py`` with 13 cases covering widget
    registration, instance numbering and settings save/restore.
  - ``test/test_main.py`` with 2 cases for the standalone entry point.
  - ``test/conftest.py`` selecting the Qt ``offscreen`` platform so the GUI
    tests run without a display server.
  - The standard ament linter tests (``flake8``, ``pep257``, ``copyright``,
    ``xmllint``).
* Added GitHub Actions CI workflow in ``.github/workflows/build.yml``.
* Added ``LICENSE`` (Apache-2.0) and ``CONTRIBUTING.md``.
* Added interface screenshot in ``doc/interface.png``.
* Contributors: Alberto Tudela
