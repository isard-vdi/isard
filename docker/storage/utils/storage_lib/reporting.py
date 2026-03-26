# SPDX-License-Identifier: AGPL-3.0-or-later

import datetime
from pathlib import Path


def get_output_dir(base="/logs/analyze"):
    """Create and return timestamped output directory."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
    output_dir = Path(f"{base}/{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_file_list(output_dir, filename, file_list):
    """Write a list of file paths to a text file.

    Returns the count of items written.
    """
    filepath = Path(output_dir) / filename
    with open(filepath, "w") as f:
        for item in sorted(file_list):
            f.write(f"{item}\n")
    return len(file_list)
