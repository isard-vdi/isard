# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test harness for the isard-changefeed AsyncAPI generator.

The generator lives at ``docker/codegen/gen_changefeed_asyncapi.py`` and is
not installable as a package — it's a standalone script shipped into the
codegen Docker image. To import it from the test module we prepend its
parent directory to ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CODEGEN_DIR = Path(__file__).resolve().parent.parent
if str(_CODEGEN_DIR) not in sys.path:
    sys.path.insert(0, str(_CODEGEN_DIR))
