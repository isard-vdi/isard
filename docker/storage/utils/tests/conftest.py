#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The operator tools import ``storage_lib`` as a top-level package because they
run from their own directory. Put that directory on the path so the tests import
the same modules the tools do."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
