#!/usr/bin/env python3
"""
OVS Worker Daemon - Smart event processing with Unix socket

This daemon receives VM lifecycle events from the qemu hook via Unix socket
and applies OVS flow rules using the native OVSDB API.

Key features:
- Unix socket server for immediate event reception
- Per-domain event queue with smart coalescing
- Delayed processing (2s) to detect rapid start→stop sequences
- In-memory flow cache for fast cleanup
- Sequential OVS operations to avoid overloading OVSDB
- Comprehensive logging with timing metrics
"""
import json
import os
import re
import socket
import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from xml.etree import ElementTree as ET

from ovs import poller as ovs_poller
from ovs.db import idl as ovs_idl

# Configuration
SOCKET_PATH = "/var/run/openvswitch/ovs-worker.sock"
OVSDB_SOCKET = "unix:/var/run/openvswitch/db.sock"
OVSDB_SCHEMA = "/usr/share/openvswitch/vswitch.ovsschema"
LOG_FILE = Path("/tmp/qemu-hook.log")
BRIDGE = "ovsbr0"
COALESCE_DELAY = 2  # Seconds to wait before processing started events


def now_ms() -> int:
    """Get current time in milliseconds"""
    return int(time.time() * 1000)


def log(data: dict):
    """Append JSON log entry to log file"""
    data["time"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")
    except Exception:
        pass  # Don't fail on log errors


@dataclass
class DomainState:
    """Track state and pending events for a domain"""

    events: list = field(default_factory=list)  # Pending events
    timer: threading.Timer = None  # Delayed processing timer
    flows: list = field(default_factory=list)  # In-memory flow rules
    running: bool = False  # Is domain currently running


class OvsWorker:
    """Worker daemon that processes qemu hook events via OVSDB"""

    def __init__(self):
        self.domains: dict[str, DomainState] = defaultdict(DomainState)
        self.lock = threading.Lock()
        self.process_queue: Queue = Queue()  # Sequential OVS operations
        self.idl = None
        self.seqno = 0
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "coalesced": 0,
            "last_elapsed_ms": 0,
        }

    def start(self):
        """Initialize and start the worker"""
        self._connect_ovsdb()
        self._start_processor_thread()
        self._run_socket_server()

    def _connect_ovsdb(self):
        """Establish persistent OVSDB connection"""
        log({"event": "ovsdb_connecting", "socket": OVSDB_SOCKET})

        schema_helper = ovs_idl.SchemaHelper(location=OVSDB_SCHEMA)
        schema_helper.register_table("Port")
        schema_helper.register_table("Interface")
        schema_helper.register_table("Bridge")

        self.idl = ovs_idl.Idl(OVSDB_SOCKET, schema_helper)

        # Wait for initial sync
        while not self.idl.has_ever_connected():
            self.idl.run()
            poller = ovs_poller.Poller()
            self.idl.wait(poller)
            poller.block()

        self.seqno = self.idl.change_seqno
        log({"event": "ovsdb_connected"})

    def _run_idl(self):
        """Run IDL to process updates"""
        self.idl.run()
        if self.idl.change_seqno != self.seqno:
            self.seqno = self.idl.change_seqno

    def _start_processor_thread(self):
        """Start thread that processes OVS operations sequentially"""

        def processor():
            while True:
                try:
                    task = self.process_queue.get()
                    start_ms = now_ms()

                    task()  # Execute the OVS operation

                    self.stats["last_elapsed_ms"] = now_ms() - start_ms
                    self.stats["processed"] += 1
                    self.process_queue.task_done()
                except Exception as e:
                    log({"event": "processor_error", "error": str(e)})

        thread = threading.Thread(target=processor, daemon=True)
        thread.start()
        log({"event": "processor_started"})

    def _run_socket_server(self):
        """Main loop - Unix socket server"""
        # Remove stale socket
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)  # Allow hook to connect
        sock.listen(32)

        log({"event": "started", "socket": SOCKET_PATH})

        while True:
            try:
                conn, _ = sock.accept()
                # Handle in thread to not block accepting new connections
                threading.Thread(
                    target=self._handle_connection, args=(conn,), daemon=True
                ).start()
            except Exception as e:
                log({"event": "accept_error", "error": str(e)})

    def _handle_connection(self, conn: socket.socket):
        """Handle a single connection from hook"""
        try:
            conn.settimeout(10)
            data = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk

            if data:
                request = json.loads(data.decode())
                self._handle_event(request)
                # Hook uses fire-and-forget, no ACK needed
        except Exception as e:
            log({"event": "connection_error", "error": str(e)})
        finally:
            conn.close()

    def _handle_event(self, request: dict):
        """Handle incoming event from hook"""
        domain = request.get("domain", "unknown")
        status = request.get("status", "unknown")
        xml = request.get("xml", "")
        timestamp = request.get("timestamp", now_ms())

        with self.lock:
            state = self.domains[domain]

            # Cancel any pending timer
            if state.timer and state.timer.is_alive():
                state.timer.cancel()
                state.timer = None

            # Add event to domain's pending events
            state.events.append({"status": status, "xml": xml, "timestamp": timestamp})

            log(
                {
                    "event": "received",
                    "id": domain,
                    "status": status,
                    "count": len(state.events),
                    "queued": self.process_queue.qsize(),
                    "duration": now_ms() - timestamp,
                }
            )

            # Schedule processing based on event type
            # stopped: process immediately (cleanup should be fast)
            # started/migrate/reconnect: delay to allow coalescing
            if status == "stopped":
                self._schedule_process(domain, delay=0)
            else:
                self._schedule_process(domain, delay=COALESCE_DELAY)

    def _schedule_process(self, domain: str, delay: float):
        """Schedule processing for a domain after delay"""
        state = self.domains[domain]

        def process():
            with self.lock:
                self._process_domain(domain)

        if delay > 0:
            state.timer = threading.Timer(delay, process)
            state.timer.start()
        else:
            # Immediate processing - called while lock is already held
            # by _handle_event(), so call _process_domain() directly
            self._process_domain(domain)

    def _process_domain(self, domain: str):
        """Process all pending events for a domain - determine final action"""
        state = self.domains[domain]
        events = state.events
        state.events = []  # Clear pending
        state.timer = None

        if not events:
            return

        # Determine final desired state from events
        final_event = events[-1]
        final_status = final_event["status"]
        final_xml = final_event["xml"]

        # Calculate duration from first event
        first_timestamp = events[0]["timestamp"]
        duration = now_ms() - first_timestamp
        event_count = len(events)
        queued = self.process_queue.qsize()

        # Log coalescing if multiple events
        if event_count > 1:
            self.stats["coalesced"] += event_count - 1
            log(
                {
                    "event": "coalesced",
                    "id": domain,
                    "status": final_status,
                    "count": event_count,
                    "queued": queued,
                    "duration": duration,
                }
            )

        # Smart state transitions
        if final_status == "started":
            if state.running:
                # Already running, skip
                log(
                    {
                        "event": "skipped",
                        "id": domain,
                        "status": final_status,
                        "reason": "already_running",
                        "count": event_count,
                        "queued": queued,
                        "duration": duration,
                    }
                )
                self.stats["skipped"] += 1
            else:
                # Queue flow_add operation
                self.process_queue.put(
                    lambda d=domain, x=final_xml, c=event_count: self._flow_add(d, x, c)
                )

        elif final_status == "stopped":
            if not state.running:
                # Not running, skip
                log(
                    {
                        "event": "skipped",
                        "id": domain,
                        "status": final_status,
                        "reason": "not_running",
                        "count": event_count,
                        "queued": queued,
                        "duration": duration,
                    }
                )
                self.stats["skipped"] += 1
            else:
                # Queue flow_del operation
                self.process_queue.put(
                    lambda d=domain, c=event_count: self._flow_del(d, c)
                )

        elif final_status == "reconnect":
            # Always reapply flows
            if state.running:
                self.process_queue.put(
                    lambda d=domain, c=event_count: self._flow_del(d, c)
                )
            self.process_queue.put(
                lambda d=domain, x=final_xml, c=event_count: self._flow_add(d, x, c)
            )

    # =========================================================================
    # OVS Operations
    # =========================================================================

    def _get_port_ofport(self, port_name: str) -> int | None:
        """Get OpenFlow port number for a port using OVSDB"""
        self._run_idl()

        for interface in self.idl.tables["Interface"].rows.values():
            if interface.name == port_name:
                ofport = interface.ofport
                if ofport and len(ofport) > 0:
                    port_num = ofport[0] if isinstance(ofport, list) else ofport
                    if port_num > 0:
                        return port_num
        return None

    def _set_port_tag(self, port_name: str, tag: int):
        """Set VLAN tag on port using OVSDB transaction"""
        self._run_idl()

        for port in self.idl.tables["Port"].rows.values():
            if port.name == port_name:
                txn = ovs_idl.Transaction(self.idl)
                port.tag = tag
                status = txn.commit_block()
                if status != ovs_idl.Transaction.SUCCESS:
                    log(
                        {
                            "event": "set_port_tag_failed",
                            "port": port_name,
                            "tag": tag,
                            "status": str(status),
                        }
                    )
                return

    def _ofctl(self, *args) -> bool:
        """Execute ovs-ofctl command"""
        cmd = ["ovs-ofctl"] + list(args)
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "ofctl_error",
                    "cmd": " ".join(cmd),
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )
            return False

    def _ofctl_mod_port(self, port_num: int, action: str) -> bool:
        """Modify port properties via ovs-ofctl"""
        return self._ofctl("mod-port", BRIDGE, str(port_num), action)

    def _ofctl_del_flows(self, matches: list):
        """Delete flows by match criteria via stdin"""
        if not matches:
            return

        cmd = ["ovs-ofctl", "del-flows", BRIDGE, "-"]
        try:
            subprocess.run(
                cmd, input="\n".join(matches).encode(), check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "ofctl_del_error",
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )

    def _parse_interfaces(self, xml_str: str) -> list:
        """Parse OVS interfaces from domain XML"""
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            log({"event": "xml_parse_error", "error": str(e)})
            return []

        interfaces = []
        for iface in root.findall(".//interface"):
            vport = iface.find("virtualport")
            if vport is not None and vport.get("type") == "openvswitch":
                target = iface.find("target")
                mac = iface.find("mac")
                vlan = iface.find("vlan/tag")

                if target is not None and mac is not None:
                    interfaces.append(
                        {
                            "port": target.get("dev"),
                            "mac": mac.get("address"),
                            "vlan": vlan.get("id") if vlan is not None else None,
                        }
                    )
        return interfaces

    def _flow_add(self, domain: str, xml_str: str, count: int = 1):
        """Add flows for domain - runs in processor thread"""
        start_ms = now_ms()

        # Check for libvirt_flags metadata - skip if start_paused (test domain)
        try:
            root = ET.fromstring(xml_str)
            libvirt_flags = root.find(".//{http://isardvdi.com}libvirt_flags")
            if libvirt_flags is not None and libvirt_flags.text == "start_paused":
                log(
                    {
                        "event": "skipped",
                        "id": domain,
                        "status": "started",
                        "reason": "start_paused",
                        "count": count,
                        "queued": self.process_queue.qsize(),
                        "duration": now_ms() - start_ms,
                    }
                )
                return
        except ET.ParseError:
            pass  # Continue with normal processing if XML parse fails

        interfaces = self._parse_interfaces(xml_str)
        if not interfaces:
            log(
                {
                    "event": "flow_add",
                    "id": domain,
                    "status": "started",
                    "count": count,
                    "queued": self.process_queue.qsize(),
                    "interfaces": 0,
                    "duration": now_ms() - start_ms,
                }
            )
            return

        flows = []
        vlan4095_count = 0

        for iface in interfaces:
            port = iface["port"]
            mac = iface["mac"]
            vlan = iface["vlan"]

            if not port or not mac:
                continue

            # Get OpenFlow port number
            nport = self._get_port_ofport(port)
            if not nport:
                log({"event": "port_not_found", "port": port, "domain": domain})
                continue

            # ==============================================================
            # MAC Spoofing Protection (ALL OVS interfaces)
            # ==============================================================
            # Allow traffic with correct source MAC -> NORMAL switching
            flows.append(f"priority=198,in_port={nport},dl_src={mac},actions=NORMAL")
            # Drop all other traffic from this port (wrong source MAC)
            flows.append(f"priority=197,in_port={nport},actions=drop")

            # ==============================================================
            # STP/BPDU Protection (ALL OVS interfaces)
            # ==============================================================
            # Drop STP BPDU frames - prevent spanning tree manipulation
            flows.append(
                f"priority=250,in_port={nport},dl_dst=01:80:c2:00:00:00,actions=drop"
            )

            # ==============================================================
            # Broadcast/Multicast Rate Limiting (ALL OVS interfaces)
            # ==============================================================
            # Rate-limit broadcasts (meter 3: 10 pkt/s, burst 50)
            flows.append(
                f"priority=190,in_port={nport},dl_dst=ff:ff:ff:ff:ff:ff,actions=meter:3,NORMAL"
            )
            # Rate-limit multicast (meter 4: 10 pkt/s, burst 50)
            flows.append(
                f"priority=190,in_port={nport},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,actions=meter:4,NORMAL"
            )

            # ==============================================================
            # VLAN 4095 Special Handling (Infrastructure Network)
            # ==============================================================
            if vlan == "4095":
                vlan4095_count += 1

                # Set port as access port with VLAN 4095 via OVSDB
                self._set_port_tag(port, 4095)

                # Disable flooding for VLAN 4095 ports (explicit delivery via p221)
                self._ofctl_mod_port(nport, "no-flood")

                # ARP requests to infrastructure (10.2.0.0/28) - rate limited
                flows.append(
                    f"priority=206,arp,in_port={nport},dl_src={mac},arp_op=1,arp_tpa=10.2.0.0/28,actions=meter:2,NORMAL"
                )
                # ARP replies - rate limited
                flows.append(
                    f"priority=206,arp,in_port={nport},dl_src={mac},arp_op=2,actions=meter:2,NORMAL"
                )

                # DHCP requests from guest (discover/request are broadcasts)
                flows.append(
                    f"priority=206,udp,in_port={nport},dl_src={mac},tp_src=68,tp_dst=67,actions=NORMAL"
                )

                # Block ALL other broadcast traffic from this port
                flows.append(
                    f"priority=205,in_port={nport},dl_dst=ff:ff:ff:ff:ff:ff,actions=drop"
                )

                # Block ALL multicast traffic from this port
                flows.append(
                    f"priority=205,in_port={nport},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,actions=drop"
                )

                # RA Guard - Block all IPv6 traffic on VLAN 4095
                flows.append(
                    f"priority=205,in_port={nport},dl_type=0x86dd,dl_src={mac},actions=drop"
                )

                # Deliver traffic from VPN to guest - strip VLAN tag before output
                flows.append(
                    f"priority=221,dl_dst={mac},dl_vlan=4095,actions=strip_vlan,output:{nport}"
                )

        # Apply flows
        if flows:
            flow_file = Path(f"/tmp/flows-{domain}")
            flow_file.write_text("\n".join(flows) + "\n")
            self._ofctl("-O", "OpenFlow13", "add-flows", BRIDGE, str(flow_file))
            flow_file.unlink()

        # Store in memory for cleanup
        with self.lock:
            self.domains[domain].flows = flows
            self.domains[domain].running = True

        log(
            {
                "event": "flow_add",
                "id": domain,
                "status": "started",
                "count": count,
                "queued": self.process_queue.qsize(),
                "interfaces": len(interfaces),
                "flows": len(flows),
                "duration": now_ms() - start_ms,
            }
        )

    def _flow_del(self, domain: str, count: int = 1):
        """Delete flows for domain using in-memory cache"""
        start_ms = now_ms()

        with self.lock:
            flows = self.domains[domain].flows.copy()
            self.domains[domain].flows = []
            self.domains[domain].running = False

        if flows:
            # Convert to delete format (remove priority and actions)
            del_matches = []
            for flow in flows:
                match_part = re.sub(r"^priority=\d+,", "", flow)
                match_part = re.sub(r",actions=.*$", "", match_part)
                del_matches.append(match_part)

            self._ofctl_del_flows(del_matches)

        log(
            {
                "event": "flow_del",
                "id": domain,
                "status": "stopped",
                "count": count,
                "queued": self.process_queue.qsize(),
                "flows": len(flows),
                "duration": now_ms() - start_ms,
            }
        )


def main():
    """Entry point"""
    log(
        {
            "event": "init",
            "coalesce_delay": COALESCE_DELAY,
            "socket": SOCKET_PATH,
            "ovsdb": OVSDB_SOCKET,
        }
    )

    worker = OvsWorker()
    worker.start()


if __name__ == "__main__":
    main()
