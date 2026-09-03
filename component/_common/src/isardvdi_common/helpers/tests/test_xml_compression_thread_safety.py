#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Concurrency test for ``isardvdi_common.helpers.xml_compression``."""

import subprocess
import sys
from pathlib import Path

CRASHER = Path(__file__).with_name("_xml_compression_thread_crasher.py")


class TestConcurrentCompression:
    def test_many_threads_survive_and_round_trip(self):
        # Out of process on purpose: sharing a zstd context across threads
        # segfaults the interpreter, which no in-process assertion survives.
        result = subprocess.run(
            [sys.executable, str(CRASHER)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"threaded compress/decompress did not survive: "
            f"exit={result.returncode} "
            f"(negative = killed by that signal)\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
