#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Transparent zstd compression for the ``domains.xml`` field.

The ``xml`` column is opaque to ReQL (never indexed, filtered, or
matched), so it can safely live as compressed binary on disk. New
writes go through :func:`compress_xml` (str → ``r.binary(zstd)``);
reads go through :func:`decompress_xml` (bytes → str, str → str
passthrough so legacy uncompressed rows keep working).

Detection is type-based: bytes-like → decompress, str → legacy
passthrough. Disjoint types, no envelope or schema marker.

Format: raw zstd frame (magic ``\\x28\\xb5\\x2f\\xfd``). Stored via
``r.binary()`` so the wire / on-disk representation is rdb's native
binary type.
"""

import logging
import os
import threading

import zstandard as zstd

log = logging.getLogger(__name__)

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning(
            "xml_compression.%s=%r not an int; using default %d", name, raw, default
        )
        return default
    return max(lo, min(hi, value))


_LEVEL = _int_env("ISARD_XML_ZSTD_LEVEL", 3, lo=1, hi=19)
_MIN_BYTES = _int_env("ISARD_XML_ZSTD_MIN_BYTES", 512, lo=0, hi=10 * 1024 * 1024)

_compressor = zstd.ZstdCompressor(level=_LEVEL)
_decompressor = zstd.ZstdDecompressor()
_lazy_lock = threading.Lock()


def is_compressed(value) -> bool:
    """``True`` iff ``value`` is bytes-like and starts with the zstd magic.

    Used by the offline migration script to skip rows that are already
    compressed.
    """
    if not isinstance(value, (bytes, bytearray, memoryview)):
        return False
    head = bytes(value[:4]) if len(value) >= 4 else b""
    return head == ZSTD_MAGIC


def compress_xml(text):
    """Wrap ``text`` for storage in ``domains.xml``.

    * ``str`` ≥ ``ISARD_XML_ZSTD_MIN_BYTES`` → ``r.binary(<zstd frame>)``,
      ready to drop into a RethinkDB ``insert`` / ``update`` payload.
    * ``str`` shorter than the threshold → unchanged ``str`` (overhead
      not worth it).
    * ``None`` → ``None``.
    * ``bytes`` already-compressed → returned untouched (idempotent for
      callers that re-stage a pre-compressed value).

    The rethinkdb import is local so unit tests that don't touch the
    rdb driver can import this module without pulling it in.
    """
    if text is None:
        return None
    if isinstance(text, (bytes, bytearray, memoryview)):
        # Already-binary value — assume caller passed an r.binary or
        # the raw bytes that came back from a previous read. Don't
        # recompress.
        return text
    if not isinstance(text, str):
        raise TypeError(f"compress_xml expected str, got {type(text).__name__}")
    encoded = text.encode("utf-8")
    if len(encoded) < _MIN_BYTES:
        return text
    from rethinkdb import r

    return r.binary(_compressor.compress(encoded))


def decompress_xml(value):
    """Normalize a stored ``xml`` value to ``str`` for callers.

    Accepts:

    * ``bytes`` / ``bytearray`` / ``memoryview`` — decoded as a zstd
      frame and returned as ``str``.
    * ``str`` — returned unchanged (legacy uncompressed rows).
    * ``None`` — returned as ``None``.

    Bytes-like values without the zstd magic prefix are logged at
    warning level and decoded as plain UTF-8 (best-effort). This keeps
    a legacy / corrupted row readable rather than blowing up the
    caller.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"decompress_xml expected str/bytes/None, got {type(value).__name__}"
        )
    raw = bytes(value)
    if not raw:
        return ""
    if raw[:4] != ZSTD_MAGIC:
        log.warning(
            "xml_compression.decompress: bytes value missing zstd magic "
            "(head=%r, len=%d); returning best-effort utf-8 decode",
            raw[:4],
            len(raw),
        )
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")
    return _decompressor.decompress(raw).decode("utf-8")


def lazy_compress_in_place(domain_id, plain_xml, *, conn):
    """Best-effort in-place migration of a legacy uncompressed row.

    Atomic: a ``r.branch`` checks the stored xml is still ``STRING``
    type before swapping it for the compressed binary, so a concurrent
    writer (editor merge, parallel domain start, offline script) that
    already converted the row turns this call into a no-op. Any failure
    is logged at warning and silently absorbed — the read caller must
    never block on this side-effect.

    Engine-only path: the caller is responsible for choosing a
    connection (typically the same one already used to fetch the row).
    """
    if not domain_id or not plain_xml or not isinstance(plain_xml, str):
        return
    encoded = plain_xml.encode("utf-8")
    if len(encoded) < _MIN_BYTES:
        return
    try:
        from rethinkdb import r

        compressed = _compressor.compress(encoded)
        with _lazy_lock:
            r.table("domains").get(domain_id).update(
                lambda row: r.branch(
                    row["xml"].type_of().eq("STRING"),
                    {"xml": r.binary(compressed)},
                    {},
                )
            ).run(conn)
    except Exception as exc:  # noqa: BLE001 — best-effort path
        log.warning(
            "xml_compression.lazy_compress_in_place failed for %s: %s",
            domain_id,
            str(exc)[:200],
        )
