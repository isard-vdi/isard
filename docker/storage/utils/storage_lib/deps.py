#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which disks must never be rewritten because something reads through them."""


def split_backing_files(files, reverse_map):
    """Split ``files`` into the ones safe to rewrite and the ones that back another disk.

    An overlay reads from its backing file every cluster it has not written
    itself, so any operation that rewrites a backing file changes what its
    children see. ``virt-sparsify --in-place`` does exactly that -- it mounts the
    guest filesystems read-write and discards everything they call free -- and so
    does a ``qemu-img convert`` that replaces the original. Neither leaves a
    trace: the virtual size, the path and the children's backing pointers are all
    unchanged, and ``qemu-img check`` on a child still passes.

    A path filter is not a substitute for this check. Matching a literal
    templates directory misses a template held in a per-category storage pool,
    and it also protects childless templates that are perfectly safe to optimize.
    What matters is not where a disk lives but whether anything reads through it.

    :param files: candidate paths
    :type files: iterable of str
    :param reverse_map: the dependency map keyed by the paths that are used as a
        backing file (its values are irrelevant here)
    :type reverse_map: dict or set
    :return: ``(safe, protected)``, both in the input order
    :rtype: tuple(list, list)
    """
    backing = set(reverse_map or ())
    safe = [f for f in files if f not in backing]
    protected = [f for f in files if f in backing]
    return safe, protected
