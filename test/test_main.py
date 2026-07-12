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
Unit tests for the standalone entry point.

``main()`` only wires the plugin into rqt, so the rqt application class is
replaced by a stub: the test asserts on the arguments it receives instead of
actually opening a window.
"""

from rqt_lifecycle_manager import main as main_module


class _FakeRqtMain:
    """Stub of ``rqt_gui.main.Main`` capturing how it is launched."""

    calls = []

    def main(self, argv, standalone=None):
        """Record the launch arguments and report a clean exit code."""
        _FakeRqtMain.calls.append((argv, standalone))
        return 0


def test_main_launches_the_plugin_standalone(monkeypatch):
    """main() starts rqt with this plugin as the standalone one."""
    _FakeRqtMain.calls = []
    monkeypatch.setattr(main_module, 'Main', _FakeRqtMain)

    exit_code = main_module.main()

    assert exit_code == 0
    assert len(_FakeRqtMain.calls) == 1
    _, standalone = _FakeRqtMain.calls[0]
    assert standalone == main_module.PLUGIN


def test_plugin_path_points_at_the_plugin_class():
    """The standalone target names the real plugin class."""
    assert main_module.PLUGIN == (
        'rqt_lifecycle_manager.lifecycle_manager_plugin.LifecycleManagerPlugin'
    )
