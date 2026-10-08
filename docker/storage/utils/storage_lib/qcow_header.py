# SPDX-License-Identifier: AGPL-3.0-or-later

"""Re-export of the qcow2 header reader, which lives in ``isardvdi_common``."""

from isardvdi_common.lib.storage.qcow_header import (  # noqa: F401
    EXT_BACKING_FORMAT,
    EXT_END,
    INCOMPAT_CORRUPT,
    INCOMPAT_DIRTY,
    KNOWN_INCOMPATIBLE,
    MAX_BACKING_NAME,
    QCOW2_MAGIC,
    V2_HEADER_LENGTH,
    Qcow2Header,
    Qcow2HeaderError,
    backing_file,
    full_backing_filename,
    read_header,
)
