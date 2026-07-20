# SPDX-License-Identifier: AGPL-3.0-or-later

"""Make the storage-worker ``task`` module importable from tests.

The worker runs as ``rq worker`` with ``docker/storage/task`` on the path
(no src layout, no package ``__init__``), so add that directory to
``sys.path`` for the test process too.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
