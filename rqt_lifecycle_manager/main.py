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
Standalone entry point for the rqt Lifecycle Manager plugin.

Running this launches the plugin on its own through ``rqt_gui`` instead of the
generic ``rqt`` container, which is convenient during development.
"""

from __future__ import annotations

import sys

from rqt_gui.main import Main

PLUGIN = (
    'rqt_lifecycle_manager.lifecycle_manager_plugin.LifecycleManagerPlugin'
)


def main(args=None) -> int:
    """
    Run the Lifecycle Manager as a standalone rqt application.

    Parameters
    ----------
    args : list, optional
        Unused; command-line arguments are read from ``sys.argv``.

    Returns
    -------
    int
        The process exit code returned by rqt.

    """
    app = Main()
    return app.main(sys.argv, standalone=PLUGIN)


if __name__ == '__main__':
    sys.exit(main())
