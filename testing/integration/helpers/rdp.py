# SPDX-License-Identifier: AGPL-3.0-or-later

"""A fake RDP guest run inside isard-vpn, and a minimal MS-TSGU client for rdpgw.

The guest flavours answer the X.224 negotiation as Windows does with
SecurityLayer=0 (``rdp``), TLS without NLA (``tls``) and NLA required (``nla``).
"""

from __future__ import annotations

import base64
import os
import socket
import ssl
import struct
import subprocess
import textwrap

# requestedProtocols / selectedProtocol bits
PROTOCOL_RDP = 0x00
PROTOCOL_SSL = 0x01
PROTOCOL_HYBRID = 0x02
PROTOCOL_HYBRID_EX = 0x08
# what the vpn RDP checks and mstsc offer
CLIENT_OFFER = PROTOCOL_SSL | PROTOCOL_HYBRID | PROTOCOL_HYBRID_EX

FAKE_GUEST = textwrap.dedent(
    """
    import socket, struct, sys, threading, time
    ip, flavour, lifetime = sys.argv[1], sys.argv[2], float(sys.argv[3])

    def x224_cc(kind, value):
        neg = struct.pack("<BBHI", kind, 0, 8, value)
        tpdu = bytes([6 + len(neg), 0xD0, 0, 0, 0, 0, 0]) + neg
        return bytes([3, 0]) + struct.pack(">H", 4 + len(tpdu)) + tpdu

    def answer(requested):
        if flavour == "rdp":
            if requested & 0x0B:
                return x224_cc(3, 2)  # SSL_NOT_ALLOWED_BY_SERVER
            return x224_cc(2, 0)
        if flavour == "tls":
            return x224_cc(2, 1) if requested & 1 else x224_cc(3, 1)
        if requested & 0x08:
            return x224_cc(2, 8)
        if requested & 0x02:
            return x224_cc(2, 2)
        return x224_cc(3, 5)  # HYBRID_REQUIRED_BY_SERVER

    def serve(conn):
        with conn:
            conn.settimeout(10)
            data = b""
            try:
                while len(data) < 4 or len(data) < struct.unpack(">H", data[2:4])[0]:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    data += chunk
            except OSError:
                return
            requested = struct.unpack("<I", data[-4:])[0] if len(data) >= 19 else 0
            conn.sendall(answer(requested))
            time.sleep(1)

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((ip, 3389))
    srv.listen(16)
    srv.settimeout(1)
    deadline = time.monotonic() + lifetime
    while time.monotonic() < deadline:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        threading.Thread(target=serve, args=(conn,), daemon=True).start()
    """
)


def start_fake_guest(container: str, ip: str, flavour: str, lifetime: int = 600):
    """Start a fake RDP guest on ``ip``:3389 inside ``container``; it exits on its own."""
    subprocess.run(
        [
            "docker",
            "exec",
            "-d",
            container,
            "python3",
            "-c",
            FAKE_GUEST,
            ip,
            flavour,
            str(lifetime),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def x224_request(requested: int) -> bytes:
    """An X.224 Connection Request with an RDP negotiation request."""
    cookie = b"Cookie: mstshash=integration\r\n"
    neg = struct.pack("<BBHI", 1, 0, 8, requested)
    tpdu = bytes([6 + len(cookie) + len(neg), 0xE0, 0, 0, 0, 0, 0]) + cookie + neg
    return bytes([3, 0]) + struct.pack(">H", 4 + len(tpdu)) + tpdu


def x224_answer(data: bytes) -> tuple[str, int]:
    """("selected", protocol) or ("failure", code) from an X.224 Connection Confirm."""
    if len(data) < 11 or data[0] != 3 or data[5] != 0xD0:
        raise ValueError(f"not an X.224 Connection Confirm: {data.hex()}")
    if len(data) < 19:
        return "selected", PROTOCOL_RDP
    kind, value = data[11], struct.unpack("<I", data[15:19])[0]
    return ("selected" if kind == 2 else "failure"), value


# MS-TSGU packet types and the PAA authentication capability
PKT_HANDSHAKE_REQUEST = 0x1
PKT_HANDSHAKE_RESPONSE = 0x2
PKT_TUNNEL_CREATE = 0x4
PKT_TUNNEL_RESPONSE = 0x5
PKT_TUNNEL_AUTH = 0x6
PKT_TUNNEL_AUTH_RESPONSE = 0x7
PKT_CHANNEL_CREATE = 0x8
PKT_CHANNEL_RESPONSE = 0x9
PKT_DATA = 0xA
PKT_CLOSE_CHANNEL = 0x10
HTTP_EXTENDED_AUTH_PAA = 0x02
HTTP_TUNNEL_PACKET_FIELD_PAA_COOKIE = 0x1


class GatewayError(Exception):
    """rdpgw refused a step; ``step`` names it and ``code`` is the HRESULT."""

    def __init__(self, step: str, code: int):
        super().__init__(f"{step}: 0x{code:08x}")
        self.step = step
        self.code = code


class RdGateway:
    """A minimal MS-TSGU (websocket transport) client."""

    def __init__(self, host: str, port: int, timeout: float = 15.0):
        context = ssl.create_default_context()
        # rdpgw serves the portal certificate, issued for the public domain
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((host, port), timeout=timeout)
        self.sock = context.wrap_socket(raw, server_hostname=host)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"RDG_OUT_DATA /remoteDesktopGateway/ HTTP/1.1\r\nHost: {host}\r\n"
                "Connection: Upgrade\r\nUpgrade: websocket\r\n"
                f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n"
                f"RDG-Connection-Id: {{{os.urandom(8).hex()}}}\r\n\r\n"
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                break
            head += chunk
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise GatewayError(f"websocket upgrade ({status!r})", 0)

    def close(self):
        self.sock.close()

    def _recvn(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise EOFError("rdpgw closed the connection")
            data += chunk
        return data

    def _send(self, ptype: int, body: bytes = b""):
        payload = struct.pack("<HHI", ptype, 0, len(body) + 8) + body
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            head = bytes([0x82, 0x80 | n])
        else:
            head = bytes([0x82, 0x80 | 126]) + struct.pack(">H", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(head + mask + masked)

    def _recv(self) -> tuple[int, bytes]:
        b0, b1 = self._recvn(2)
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recvn(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recvn(8))[0]
        frame = self._recvn(n)
        ptype, _, size = struct.unpack("<HHI", frame[:8])
        return ptype, frame[8:size]

    def _expect(self, step: str, want: int, offset: int) -> bytes:
        ptype, body = self._recv()
        if ptype != want:
            raise GatewayError(f"{step} (packet 0x{ptype:x})", 0)
        code = struct.unpack("<I", body[offset : offset + 4])[0]
        if code:
            raise GatewayError(step, code)
        return body

    def open_channel(self, token: str, guest: str, port: int = 3389):
        """Handshake, tunnel and channel to ``guest``:``port`` with a viewer token."""
        self._send(
            PKT_HANDSHAKE_REQUEST, struct.pack("<BBHH", 1, 0, 0, HTTP_EXTENDED_AUTH_PAA)
        )
        self._expect("handshake", PKT_HANDSHAKE_RESPONSE, 0)
        cookie = token.encode("utf-16-le")
        self._send(
            PKT_TUNNEL_CREATE,
            struct.pack("<IHH", 0, HTTP_TUNNEL_PACKET_FIELD_PAA_COOKIE, 0)
            + struct.pack("<H", len(cookie))
            + cookie,
        )
        self._expect("tunnel", PKT_TUNNEL_RESPONSE, 2)
        name = "integration".encode("utf-16-le")
        self._send(PKT_TUNNEL_AUTH, struct.pack("<H", len(name)) + name)
        self._expect("tunnel auth", PKT_TUNNEL_AUTH_RESPONSE, 0)
        server = guest.encode("utf-16-le")
        self._send(
            PKT_CHANNEL_CREATE,
            struct.pack("<BBHH", 1, 0, port, 3)
            + struct.pack("<H", len(server))
            + server,
        )
        self._expect("channel", PKT_CHANNEL_RESPONSE, 0)

    def rdp_exchange(self, data: bytes) -> bytes:
        """Send one RDP packet to the guest through the channel, return its answer."""
        self._send(PKT_DATA, struct.pack("<H", len(data)) + data)
        ptype, body = self._recv()
        if ptype == PKT_CLOSE_CHANNEL:
            raise EOFError("rdpgw closed the channel")
        if ptype != PKT_DATA:
            raise GatewayError(f"data (packet 0x{ptype:x})", 0)
        size = struct.unpack("<H", body[:2])[0]
        return body[2 : 2 + size]
