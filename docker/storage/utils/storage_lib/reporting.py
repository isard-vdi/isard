# SPDX-License-Identifier: AGPL-3.0-or-later

import datetime
import os
from pathlib import Path


def get_output_dir(base="/logs/analyze"):
    """Create and return timestamped output directory."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
    output_dir = Path(f"{base}/{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_file_list(output_dir, filename, file_list):
    """Write a list of file paths to a text file plus a metadata sidecar.

    The plain `.txt` file keeps one path per line so existing `xargs rm`
    recipes keep working. Alongside it we write `<name>.meta.tsv` with
    `path<TAB>size_bytes<TAB>mtime_iso` for every path that still exists
    on disk, so later analysis can bucketize by size and age.

    Returns the count of items written to the .txt file.
    """
    out = Path(output_dir)
    txt_path = out / filename
    with open(txt_path, "w") as f:
        for item in sorted(file_list):
            f.write(f"{item}\n")

    meta_path = out / f"{Path(filename).stem}.meta.tsv"
    with open(meta_path, "w") as f:
        f.write("path\tsize_bytes\tmtime_iso\n")
        for item in sorted(file_list):
            try:
                st = os.stat(item)
            except (OSError, TypeError):
                continue
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).isoformat(
                timespec="seconds"
            )
            f.write(f"{item}\t{st.st_size}\t{mtime}\n")

    return len(file_list)
