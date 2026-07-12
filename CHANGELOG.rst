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
* Added unit tests in ``test/test_lifecycle_manager.py`` (3 test cases) and the
  standard ament linter tests (all 7 tests pass under ROS 2 Jazzy).
* Added GitHub Actions CI workflow in ``.github/workflows/build.yml``.
* Added ``LICENSE`` (Apache-2.0) and ``CONTRIBUTING.md``.
* Added interface screenshot in ``doc/interface.png``.
* Contributors: Alberto Tudela
