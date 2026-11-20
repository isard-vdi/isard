# SPDX-License-Identifier: AGPL-3.0-or-later

"""A minimal stdlib SPICE client: link, ticket auth and the first display image.

The ticket is RSA-OAEP(SHA1) with the server's key, done on hashlib + ``pow`` so
the suite needs no crypto dependency.
"""

from __future__ import annotations

import hashlib
import os
import socket
import struct

SPICE_MAGIC = b"REDQ"
VERSION_MAJOR, VERSION_MINOR = 2, 2
PUBKEY_BYTES = 162

CHANNEL_MAIN = 1
CHANNEL_DISPLAY = 2

CAP_AUTH_SELECTION = 0
CAP_AUTH_SPICE = 1

LINK_OK = 0  # anything else from the ticket step is a rejection

MSG_SET_ACK = 3  # common
MSGC_ACK_SYNC = 1  # common
MSG_MAIN_INIT = 103
MSGC_DISPLAY_INIT = 101

# display messages that mean the server is painting a surface: marks, draws,
# surface/monitor setup and streams. Receiving any one is the "first image".
DISPLAY_IMAGE_MSGS = frozenset({102, 122} | set(range(302, 318)))


def _mgf1(seed: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hashlib.sha1(seed + struct.pack(">I", counter)).digest()
        counter += 1
    return out[:length]


def _der_rsa_pubkey(der: bytes) -> tuple[int, int]:
    """(modulus, exponent) from a DER SubjectPublicKeyInfo for an RSA key."""

    def tlv(buf: bytes, i: int):
        length = buf[i + 1]
        i += 2
        if length & 0x80:
            k = length & 0x7F
            length = int.from_bytes(buf[i : i + k], "big")
            i += k
        return buf[i : i + length], i + length

    spki, _ = tlv(der, 0)
    _, after_alg = tlv(spki, 0)  # skip AlgorithmIdentifier
    bitstring, _ = tlv(spki, after_alg)
    rsa_key, _ = tlv(bitstring[1:], 0)  # drop the unused-bits byte
    modulus, after_n = tlv(rsa_key, 0)
    exponent, _ = tlv(rsa_key, after_n)
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


def _rsa_oaep(pubkey_der: bytes, message: bytes) -> bytes:
    n, e = _der_rsa_pubkey(pubkey_der)
    k = (n.bit_length() + 7) // 8
    h = 20  # SHA-1
    if len(message) > k - 2 * h - 2:
        raise ValueError("ticket too long for OAEP")
    l_hash = hashlib.sha1(b"").digest()
    db = l_hash + b"\x00" * (k - len(message) - 2 * h - 2) + b"\x01" + message
    seed = os.urandom(h)
    db_mask = _mgf1(seed, k - h - 1)
    masked_db = bytes(a ^ b for a, b in zip(db, db_mask))
    masked_seed = bytes(a ^ b for a, b in zip(seed, _mgf1(masked_db, h)))
    em = b"\x00" + masked_seed + masked_db
    return pow(int.from_bytes(em, "big"), e, n).to_bytes(k, "big")


class SpiceError(Exception):
    pass


class _Channel:
    def __init__(self, host, port, channel_type, connection_id, ticket, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._link(connection_id, channel_type)
        self._auth(ticket)

    def _recvn(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise EOFError("spice server closed the connection")
            data += chunk
        return data

    def _link(self, connection_id, channel_type):
        caps = (1 << CAP_AUTH_SELECTION) | (1 << CAP_AUTH_SPICE)
        mess = struct.pack(
            "<IBBIII", connection_id, channel_type, 0, 1, 0, 18
        ) + struct.pack("<I", caps)
        header = SPICE_MAGIC + struct.pack(
            "<III", VERSION_MAJOR, VERSION_MINOR, len(mess)
        )
        self.sock.sendall(header + mess)

        reply_header = self._recvn(16)
        if reply_header[:4] != SPICE_MAGIC:
            raise SpiceError(f"bad magic in link reply: {reply_header[:4]!r}")
        reply = self._recvn(struct.unpack("<I", reply_header[12:16])[0])
        (error,) = struct.unpack("<I", reply[:4])
        if error != LINK_OK:
            raise SpiceError(f"link error {error}")
        self.pubkey = reply[4 : 4 + PUBKEY_BYTES]

    def _auth(self, ticket):
        self.sock.sendall(struct.pack("<I", CAP_AUTH_SPICE))
        self.sock.sendall(_rsa_oaep(self.pubkey, ticket.encode() + b"\x00"))
        (result,) = struct.unpack("<I", self._recvn(4))
        if result != LINK_OK:
            raise SpiceError(f"ticket rejected: link result {result}")

    def recv_msg(self) -> tuple[int, bytes]:
        _serial, mtype, size, _sub = struct.unpack("<QHII", self._recvn(18))
        return mtype, self._recvn(size)

    def send_msg(self, mtype: int, body: bytes = b"") -> None:
        self.sock.sendall(struct.pack("<QHII", 1, mtype, len(body), 0) + body)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def first_display_image(host, port, ticket, timeout=20.0, budget=200) -> int:
    """Link MAIN + DISPLAY and return the type of the first display image.

    Raises ``SpiceError`` if the ticket is rejected (the negative control)."""
    main = _Channel(host, port, CHANNEL_MAIN, 0, ticket, timeout)
    session_id = None
    for _ in range(budget):
        mtype, body = main.recv_msg()
        if mtype == MSG_SET_ACK:
            main.send_msg(MSGC_ACK_SYNC, body[:4])
        elif mtype == MSG_MAIN_INIT:
            (session_id,) = struct.unpack("<I", body[:4])
            break
    if session_id is None:
        main.close()
        raise SpiceError("no MAIN_INIT received")

    display = _Channel(host, port, CHANNEL_DISPLAY, session_id, ticket, timeout)
    # pixmap cache + GLZ dictionary hints; the values only size caches we never
    # fill, but the server waits for INIT before pushing the screen.
    display.send_msg(MSGC_DISPLAY_INIT, struct.pack("<BqBi", 1, 10 << 20, 1, 1 << 20))
    try:
        for _ in range(budget):
            mtype, body = display.recv_msg()
            if mtype == MSG_SET_ACK:
                display.send_msg(MSGC_ACK_SYNC, body[:4])
            elif mtype in DISPLAY_IMAGE_MSGS:
                return mtype
        raise SpiceError("no display image within the message budget")
    finally:
        display.close()
        main.close()
