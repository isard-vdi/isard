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

import json
import logging as log
import subprocess
import threading
import time
from datetime import datetime
from typing import List, Mapping, MutableMapping, NamedTuple, Optional, Tuple

from api_client import ApiClient

try:
    apic = ApiClient()
except:
    raise


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
            latest_handshake=datetime.fromtimestamp(int(handshake_ts))
            if handshake_ts != "0"
            else None,
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
        peers = get_peer_states()
        for peer in peers:
            now_connected = is_peer_connected(peer.latest_handshake, handshake_timeout)
            payload = peer._asdict()
            ## Sample payload (We can get remote addr & port)
            ## {'device': 'users', 'name': None, 'public_key': 'k8rLxWlaD/Zq5KH5r296x+RBrI2UfdWOIAXrSxKLmjs=', 'remote_addr': '46.26.75.11:34762', 'allowed_ips': ['10.0.0.2/32'], 'latest_handshake': datetime.datetime(2021, 12, 3, 8, 12, 57), 'transfer_rx': 180, 'transfer_tx': 124}

            try:
                remote_data = payload["remote_addr"].split(":")
            except:
                remote_data = ["", -1]

            if peer.public_key not in peer_state:
                if not peer.latest_handshake:
                    peers_to_delete.append(
                        {
                            "kind": payload["device"],
                            "client_ip": payload["allowed_ips"][0].split("/")[0],
                        }
                    )
                else:
                    log.debug("POST: 1, NEW PEER FOUND, NOT PREVIOUSLY IN PEER STATE")
                    apic.post(
                        "vpn_connection/"
                        + payload["device"]
                        + "/"
                        + payload["allowed_ips"][0].split("/")[0],
                        {
                            "remote_ip": remote_data[0],
                            "remote_port": int(remote_data[1]),
                        },
                    )
                peer_state[peer.public_key] = (
                    now_connected,
                    peer.latest_handshake,
                    peer.remote_addr,
                )
                continue
            previously_connected, previous_handshake, remote_addr = peer_state[
                peer.public_key
            ]
            if previously_connected and not now_connected:
                log.debug("DELETE: 2, NOT CONNECTED ANYMORE")
                apic.delete(
                    "vpn_connection/"
                    + payload["device"]
                    + "/"
                    + payload["allowed_ips"][0].split("/")[0]
                )
            elif not previously_connected and now_connected:
                log.debug("POST: 2, WAS NOT CONNECTED, NOW CONNECTED")
                apic.post(
                    "vpn_connection/"
                    + payload["device"]
                    + "/"
                    + payload["allowed_ips"][0].split("/")[0],
                    {
                        "remote_ip": remote_data[0],
                        "remote_port": int(remote_data[1]),
                    },
                )
            elif previously_connected and remote_addr != peer.remote_addr:
                # Peer roamed
                log.debug(
                    "PUT: User migrated IP from "
                    + str(remote_addr)
                    + " to "
                    + str(peer.remote_addr)
                    + ".\nWARNING! If happens often could be that user is connected to the same vpn from different locations at the same time!"
                )
                apic.update(
                    "vpn_connection/"
                    + payload["device"]
                    + "/"
                    + payload["allowed_ips"][0].split("/")[0],
                    {
                        "remote_ip": remote_data[0],
                        "remote_port": int(remote_data[1]),
                    },
                )
            peer_state[peer.public_key] = (
                now_connected,
                peer.latest_handshake,
                peer.remote_addr,
            )

        if len(peers_to_delete):
            log.debug("DELETE (" + str(len(peers_to_delete)) + "): 1, LOST HANDSHAKE")
            apic.delete(
                "vpn_connections",
                data=peers_to_delete,
            )
        peers_to_delete = []
        time.sleep(poll_delay)


def start_monitoring_vpn_status():
    poll_delay = 5
    handshake_timeout = 150

    logger_thread = threading.Thread(
        target=log_wireguard_peers, args=(poll_delay, handshake_timeout)
    )
    logger_thread.start()
