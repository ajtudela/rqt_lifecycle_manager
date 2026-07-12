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
Shared pytest configuration for the rqt_lifecycle_manager test suite.

pytest imports this file before any test module, which lets us select the Qt
``offscreen`` platform plugin here. Without it, building a ``QApplication`` on
a headless machine (such as a CI runner) fails for lack of a display server.
The Qt imports below therefore have to happen after that variable is set.
"""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest  # noqa: E402
from python_qt_binding.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope='session')
def qapp():
    """Provide the single QApplication needed to build Qt widgets."""
    app = QApplication.instance() or QApplication([])
    yield app
