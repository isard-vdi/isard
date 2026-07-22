#!/usr/bin/env python3
# From https://gist.github.com/jbaiter/b9e1c5bce9567531e14a4be474c0e203
"""Wireguard logging and monitoring tool.
Logs the following events along with the peer state in JSON format to stdout:
- Peer connected (= successfull handshake after period of no handshakes)
- Peer disconnected (= no handshake for longer than 5 minutes)
- Peer roamed (= source IP of the peer changed)
Additionally, the tool exposes a Prometheus-compatible monitoring endpoint
on port 9000 that exports the following metrics:
- `wireguard_sent_bytes_total`: Bytes sent to the peer (counter)
- `wireguard_received_bytes_total`: Bytes received from the peer (counter)
- `wireguard_latest_handshake_seconds`: Seconds from the last handshake (gauge)
Requires Python >=3.7, but no additional libraries.
--------------------------------------------------------------------------------
Copyright 2020 Johannes Baiter <johannes.baiter@gmail.com>
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
Software, and to permit persons to whom the Software is furnished to do so, subject
to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
from __future__ import annotations

import logging as log
import subprocess
import threading
import time
import traceback
from datetime import datetime
from typing import List, MutableMapping, NamedTuple, Optional, Tuple

from isardvdi_apiv4_client.api.role_admin import (
    vpn_connection_connect,
    vpn_connection_disconnect,
    vpn_connection_roam,
    vpn_connections_disconnect,
)
from isardvdi_apiv4_client.models import VpnConnectionRequest, VpnDisconnectListItem
from isardvdi_apiv4_client_auth import build_client, raise_for_status


def _skip_unresolved_peer(response) -> bool:
    """Tolerate the benign per-peer 404 without poisoning the poll pass.

    Returns True when the peer was skipped (404 — its ``client_ip`` has no
    row yet), so the caller leaves ``peer_state`` unchanged and retries the
    update on a later poll instead of losing the transition; False when the
    update was applied.

    The per-peer calls in :func:`log_wireguard_peers` share a single ``for
    peer in peers`` loop, so letting one peer's error abort the pass would
    stop connected-status updates for every peer after it. A users-interface
    peer whose ``client_ip`` maps to no ``users``/``remotevpn`` row makes
    apiv4 return ``404`` — an eventually-consistent per-peer condition that
    must simply be skipped. Every other status (5xx, 401, ...) is a systemic
    failure, not a per-peer one, and is re-raised so it reaches the outer
    retry loop exactly as a transport error would.
    """
    if response.status_code == 404:
        log.warning("vpn_connection update skipped: no active client for this peer")
        return True
    raise_for_status(response)
    return False


class RemotePeer(NamedTuple):
    """State of a remote Wireguard peer."""

    device: str
    public_key: str
    remote_addr: Optional[str]
    allowed_ips: Tuple[str]
    latest_handshake: Optional[datetime]
    transfer_rx: int
    transfer_tx: int

    @classmethod
    def parse(cls, *columns) -> RemotePeer:
        """Parse a RemotePeer from a `wg show all dump` line."""
        dev, pub, _, remote_addr, ip_list, handshake_ts, bytes_rx, bytes_tx, _ = columns
        return cls(
            device=dev,
            public_key=pub,
            remote_addr=remote_addr if remote_addr != "(none)" else None,
            allowed_ips=ip_list.split(","),
            latest_handshake=(
                datetime.fromtimestamp(int(handshake_ts))
                if handshake_ts != "0"
                else None
            ),
            transfer_rx=int(bytes_rx),
            transfer_tx=int(bytes_tx),
        )


def get_peer_states() -> List[RemotePeer]:
    """Get the state of all remote peers from Wireguard."""
    wg_out = subprocess.check_output(["wg", "show", "all", "dump"]).decode("utf8")
    rows = [l.split("\t") for l in wg_out.split("\n")]
    return [RemotePeer.parse(*row) for row in rows if len(row) > 5]


def is_peer_connected(last_handshake: Optional[datetime], timeout: int) -> bool:
    if last_handshake is None:
        last_handshake = datetime.fromtimestamp(0)
    since_handshake = datetime.now() - last_handshake
    return since_handshake.total_seconds() < timeout


def log_wireguard_peers(poll_delay: int, handshake_timeout: int):
    """Poll wireguard peer state and log connections/disconnections in JSON to stdout."""
    peer_state: MutableMapping[str, Tuple[bool, Optional[datetime], Optional[str]]] = {
        peer.public_key: (
            is_peer_connected(peer.latest_handshake, handshake_timeout),
            peer.latest_handshake,
            peer.remote_addr,
        )
        for peer in get_peer_states()
    }

    #  or not peer.latest_handshake
    t = threading.currentThread()
    peers_to_delete = []
    while True:
        try:
            # Re-mint the JWT on each iteration to stay within the 20s TTL.
            with build_client("isard-vpn", role="hypervisor") as client:
                peers = get_peer_states()
                for peer in peers:
                    now_connected = is_peer_connected(
                        peer.latest_handshake, handshake_timeout
                    )
                    payload = peer._asdict()

                    try:
                        remote_data = payload["remote_addr"].split(":")
                    except:
                        remote_data = ["", -1]

                    kind = payload["device"]
                    client_ip = payload["allowed_ips"][0].split("/")[0]

                    if peer.public_key not in peer_state:
                        skipped = False
                        if not peer.latest_handshake:
                            peers_to_delete.append(
                                {
                                    "kind": kind,
                                    "client_ip": client_ip,
                                }
                            )
                        else:
                            log.debug(
                                "POST: 1, NEW PEER FOUND, NOT PREVIOUSLY IN PEER STATE"
                            )
                            resp = vpn_connection_connect.sync_detailed(
                                kind=kind,
                                client_ip=client_ip,
                                client=client,
                                body=VpnConnectionRequest(
                                    remote_ip=remote_data[0],
                                    remote_port=int(remote_data[1]),
                                ),
                            )
                            skipped = _skip_unresolved_peer(resp)
                        # A skipped (404) connect leaves the peer untracked so
                        # the next poll retries instead of losing the connect.
                        if not skipped:
                            peer_state[peer.public_key] = (
                                now_connected,
                                peer.latest_handshake,
                                peer.remote_addr,
                            )
                        continue
                    previously_connected, previous_handshake, remote_addr = peer_state[
                        peer.public_key
                    ]
                    skipped = False
                    if previously_connected and not now_connected:
                        log.debug("DELETE: 2, NOT CONNECTED ANYMORE")
                        resp = vpn_connection_disconnect.sync_detailed(
                            kind=kind,
                            client_ip=client_ip,
                            client=client,
                        )
                        # A 404 on disconnect means the row is already gone, so
                        # advancing to disconnected is correct; do not retry.
                        _skip_unresolved_peer(resp)
                    elif not previously_connected and now_connected:
                        log.debug("POST: 2, WAS NOT CONNECTED, NOW CONNECTED")
                        resp = vpn_connection_connect.sync_detailed(
                            kind=kind,
                            client_ip=client_ip,
                            client=client,
                            body=VpnConnectionRequest(
                                remote_ip=remote_data[0],
                                remote_port=int(remote_data[1]),
                            ),
                        )
                        skipped = _skip_unresolved_peer(resp)
                    elif previously_connected and remote_addr != peer.remote_addr:
                        # Peer roamed
                        log.debug(
                            "PUT: User migrated IP from "
                            + str(remote_addr)
                            + " to "
                            + str(peer.remote_addr)
                            + ".\nWARNING! If happens often could be that user is connected to the same vpn from different locations at the same time!"
                        )
                        resp = vpn_connection_roam.sync_detailed(
                            kind=kind,
                            client_ip=client_ip,
                            client=client,
                            body=VpnConnectionRequest(
                                remote_ip=remote_data[0],
                                remote_port=int(remote_data[1]),
                            ),
                        )
                        skipped = _skip_unresolved_peer(resp)
                    # Leave peer_state unchanged when a connect/roam was skipped
                    # (404) so the transition is retried on the next poll.
                    if not skipped:
                        peer_state[peer.public_key] = (
                            now_connected,
                            peer.latest_handshake,
                            peer.remote_addr,
                        )

                if len(peers_to_delete):
                    log.debug(
                        "DELETE (" + str(len(peers_to_delete)) + "): 1, LOST HANDSHAKE"
                    )
                    resp = vpn_connections_disconnect.sync_detailed(
                        client=client,
                        body=[
                            VpnDisconnectListItem(
                                kind=peer["kind"],
                                client_ip=peer["client_ip"],
                            )
                            for peer in peers_to_delete
                        ],
                    )
                    _skip_unresolved_peer(resp)
                peers_to_delete = []
            time.sleep(poll_delay)
        except:
            log.info("Exception in log_wireguard_peers")
            log.debug(traceback.format_exc())
            time.sleep(0.1)


def start_monitoring_vpn_status():
    poll_delay = 5
    handshake_timeout = 150

    logger_thread = threading.Thread(
        target=log_wireguard_peers, args=(poll_delay, handshake_timeout)
    )
    logger_thread.start()
