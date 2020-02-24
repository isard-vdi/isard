#!/usr/bin/env python3

import multiprocessing
import websockify
import socket
import os

try:
    websockets = int(os.getenv('WEBSOCKETS','10'))
except:
    websockets=10

servers = {}
procs = {}

for i in range(websockets):
    servers[i] = websockify.WebSocketProxy(
        listen_host="0.0.0.0",
        listen_port=6900 + i,
        target_host=socket.getfqdn(),
        target_port=5900 + i,
        cert="/etc/pki/libvirt-spice/server-cert.pem",
        key="/etc/pki/libvirt-spice/server-key.pem",
    )
    procs[i] = multiprocessing.Process(target=servers[i].start_server)
    procs[i].start()

