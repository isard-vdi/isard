# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source paths for the suites that read engine sources instead of importing them."""

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
ENGINE_SRC = SRC_ROOT / "engine"
