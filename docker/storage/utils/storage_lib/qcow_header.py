# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read the backing file of a qcow2 image from its header, without qemu-img."""

import struct
from collections import namedtuple

QCOW2_MAGIC = b"QFI\xfb"
EXT_END = 0x00000000
EXT_BACKING_FORMAT = 0xE2792ACA
# dirty, corrupt, external data file, compression type, extended L2
KNOWN_INCOMPATIBLE = 0x1F
V2_HEADER_LENGTH = 72
MAX_BACKING_NAME = 1023

Qcow2Header = namedtuple("Qcow2Header", "version backing_file backing_format")


class Qcow2HeaderError(Exception):
    pass


def _has_protocol(name):
    for ch in name:
        if ch == "/":
            return False
        if ch == ":":
            return True
    return False


def full_backing_filename(image_path, backing_file):
    """Resolve ``backing_file`` against the image's directory, as qemu does."""
    if backing_file.startswith("/") or _has_protocol(backing_file):
        return backing_file
    image_path = str(image_path)
    return image_path[: image_path.rfind("/") + 1] + backing_file


def _decode(raw, what):
    if b"\0" in raw:
        raise Qcow2HeaderError(f"{what} contains a NUL byte")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Qcow2HeaderError(f"{what} is not valid UTF-8") from e


def _read_extensions(data, start, end):
    backing_format = None
    offset = start
    while True:
        if offset + 8 > end:
            raise Qcow2HeaderError("header extensions overrun")
        ext_type, ext_len = struct.unpack_from(">II", data, offset)
        offset += 8
        if ext_type == EXT_END:
            return backing_format
        if offset + ext_len > end:
            raise Qcow2HeaderError("header extension overruns its area")
        if ext_type == EXT_BACKING_FORMAT:
            backing_format = _decode(data[offset : offset + ext_len], "backing format")
        offset += (ext_len + 7) & ~7


def read_header(path):
    """Return ``Qcow2Header``; raise ``Qcow2HeaderError`` on anything unexpected."""
    with open(path, "rb") as f:
        head = f.read(V2_HEADER_LENGTH)
        if len(head) < V2_HEADER_LENGTH:
            raise Qcow2HeaderError("file is shorter than a qcow2 header")
        if head[:4] != QCOW2_MAGIC:
            raise Qcow2HeaderError("not a qcow2 image")

        version, backing_offset, backing_size, cluster_bits = struct.unpack_from(
            ">IQII", head, 4
        )
        if version not in (2, 3):
            raise Qcow2HeaderError(f"unsupported qcow2 version {version}")
        if not 9 <= cluster_bits <= 21:
            raise Qcow2HeaderError(f"invalid cluster_bits {cluster_bits}")
        cluster_size = 1 << cluster_bits

        if version == 2:
            header_length = V2_HEADER_LENGTH
        else:
            head += f.read(104 - V2_HEADER_LENGTH)
            if len(head) < 104:
                raise Qcow2HeaderError("truncated qcow2 v3 header")
            (incompatible,) = struct.unpack_from(">Q", head, 72)
            if incompatible & ~KNOWN_INCOMPATIBLE:
                raise Qcow2HeaderError("unknown incompatible features")
            (header_length,) = struct.unpack_from(">I", head, 100)
            if header_length < 104 or header_length > cluster_size:
                raise Qcow2HeaderError(f"invalid header_length {header_length}")

        if backing_offset == 0:
            backing_file = None
        else:
            if backing_size == 0 or backing_size > MAX_BACKING_NAME:
                raise Qcow2HeaderError(f"invalid backing_file_size {backing_size}")
            if backing_offset > cluster_size - backing_size:
                raise Qcow2HeaderError("backing file name outside the first cluster")

        ext_end = backing_offset if backing_offset else cluster_size
        f.seek(0)
        data = f.read(max(ext_end, backing_offset + backing_size))

    if backing_offset:
        raw = data[backing_offset : backing_offset + backing_size]
        if len(raw) != backing_size:
            raise Qcow2HeaderError("backing file name is truncated")
        backing_file = _decode(raw, "backing file name")

    # qemu reads past the end of the file as zeros, which ends the extensions.
    data = data.ljust(ext_end, b"\0")
    backing_format = None
    if ext_end > header_length:
        backing_format = _read_extensions(data, header_length, ext_end)

    return Qcow2Header(version, backing_file, backing_format)


def backing_file(path):
    """The ``full-backing-filename`` qemu-img would report, or ``None``."""
    header = read_header(path)
    if header.backing_file is None:
        return None
    return full_backing_filename(path, header.backing_file)
