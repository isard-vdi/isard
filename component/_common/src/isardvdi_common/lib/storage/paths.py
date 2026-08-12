# SPDX-License-Identifier: AGPL-3.0-or-later

"""On-disk layout the storage worker imposes, for whoever has to read it back.

The worker decides where a disk lives; a tool that scans a pool has to
recognise those places or it will classify one of them wrong.
"""

#: Subdirectory ``move_delete`` renames a soft-deleted disk into, beside the
#: file it replaces. The name is kept, so the same uuid exists twice on disk and
#: only the location tells the live disk from the discarded copy.
RECYCLE_BIN_DIR = "deleted"
