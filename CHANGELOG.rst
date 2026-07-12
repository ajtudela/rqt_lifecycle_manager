^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package rqt_lifecycle_manager
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
  under ROS 2 Jazzy):

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
