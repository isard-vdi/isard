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
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import PriorityQueue
from xml.etree import ElementTree as ET

from ovs import poller as ovs_poller
from ovs.db import idl as ovs_idl

# Configuration
SOCKET_PATH = "/var/run/openvswitch/ovs-worker.sock"
OVSDB_SOCKET = "unix:/var/run/openvswitch/db.sock"
OVSDB_SCHEMA = "/usr/share/openvswitch/vswitch.ovsschema"
LOG_FILE = Path("/tmp/qemu-hook.log")
BRIDGE = "ovsbr0"


def now_ms() -> int:
    """Get current time in milliseconds"""
    return int(time.time() * 1000)


def log(data: dict):
    """Log JSON entry to file (tail -f streams to docker logs via start.sh)"""
    data["type"] = "ovs_worker"
    data["sysid"] = os.environ.get("HYPER_ID", "unknown")
    data["time"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(data)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass  # Don't fail on log errors


@dataclass
class DomainState:
    """Track state and pending events for a domain"""

    events: list = field(default_factory=list)  # Pending events
    flows: list = field(default_factory=list)  # In-memory flow rules
    meters: list = field(default_factory=list)  # Per-VM meter IDs
    ports: list = field(default_factory=list)  # OVS ports we manage (ethernet type)
    running: bool = False  # Is domain currently running


class OvsWorker:
    """Worker daemon that processes qemu hook events via OVSDB"""

    def __init__(self):
        self.domains: dict[str, DomainState] = defaultdict(DomainState)
        self.lock = threading.Lock()
        self.process_queue: PriorityQueue = (
            PriorityQueue()
        )  # Priority: starts before stops
        self._task_counter = (
            0  # Tie-breaker for priority queue (lambdas aren't comparable)
        )
        self.idl = None
        self.seqno = 0
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "coalesced": 0,
            "last_elapsed_ms": 0,
        }
        # Security stats collection
        self.last_stats_time = 0
        self.stats_interval = 60  # seconds

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
        from queue import Empty

        def processor():
            while True:
                try:
                    # Use timeout to allow periodic security stats collection
                    try:
                        _, _, task = self.process_queue.get(timeout=10)
                    except Empty:
                        # Queue empty - check if we should collect stats
                        now = time.time()
                        if now - self.last_stats_time >= self.stats_interval:
                            try:
                                self._collect_security_stats()
                            except Exception as e:
                                import traceback

                                log(
                                    {
                                        "event": "security_stats_error",
                                        "error": str(e),
                                        "traceback": traceback.format_exc(),
                                    }
                                )
                            self.last_stats_time = now
                        continue

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

            # Process immediately - ovs-worker creates OVS ports itself,
            # so no delay needed to wait for port creation
            self._process_domain(domain)

    def _process_domain(self, domain: str):
        """Process all pending events for a domain - determine final action"""
        state = self.domains[domain]
        events = state.events
        state.events = []  # Clear pending

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
                # Queue flow_add operation (priority 0 = high priority for starts)
                self._task_counter += 1
                self.process_queue.put(
                    (
                        0,
                        self._task_counter,
                        lambda d=domain, x=final_xml, c=event_count: self._flow_add(
                            d, x, c
                        ),
                    )
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
                # Queue flow_del operation (priority 1 = low priority for stops)
                self._task_counter += 1
                self.process_queue.put(
                    (
                        1,
                        self._task_counter,
                        lambda d=domain, c=event_count: self._flow_del(d, c),
                    )
                )

        elif final_status == "reconnect":
            # Always reapply flows
            if state.running:
                self._task_counter += 1
                self.process_queue.put(
                    (
                        1,
                        self._task_counter,
                        lambda d=domain, c=event_count: self._flow_del(d, c),
                    )
                )
            self._task_counter += 1
            self.process_queue.put(
                (
                    0,
                    self._task_counter,
                    lambda d=domain, x=final_xml, c=event_count: self._flow_add(
                        d, x, c
                    ),
                )
            )

    # =========================================================================
    # OVS Operations
    # =========================================================================

    def _get_port_ofport(self, port_name: str, retries: int = 3) -> int | None:
        """Get OpenFlow port number for a port using OVSDB with retry

        Uses short retries (200ms each) to handle OVSDB IDL sync lag.
        Port is added by _add_port_to_ovs() before this is called.
        """
        for attempt in range(retries):
            # Poll IDL for updates
            poller = ovs_poller.Poller()
            self.idl.wait(poller)
            poller.timer_wait(50)  # 50ms max wait for updates
            poller.block()
            self.idl.run()

            for interface in self.idl.tables["Interface"].rows.values():
                if interface.name == port_name:
                    ofport = interface.ofport
                    if ofport and len(ofport) > 0:
                        port_num = ofport[0] if isinstance(ofport, list) else ofport
                        if port_num > 0:
                            return port_num

            # Port not found yet, short wait before retry
            if attempt < retries - 1:
                time.sleep(0.2)

        return None

    def _set_port_tag(self, port_name: str, tag: int):
        """Set VLAN tag on port using OVSDB transaction"""
        self._run_idl()

        for port in self.idl.tables["Port"].rows.values():
            if port.name == port_name:
                txn = ovs_idl.Transaction(self.idl)
                port.tag = tag
                status = txn.commit_block()
                # UNCHANGED is expected if tag already set, not an error
                if status not in (
                    ovs_idl.Transaction.SUCCESS,
                    ovs_idl.Transaction.UNCHANGED,
                ):
                    log(
                        {
                            "event": "set_port_tag_error",
                            "port": port_name,
                            "tag": tag,
                            "status": str(status),
                        }
                    )
                return

    def _get_bridge(self, bridge_name: str = BRIDGE):
        """Get bridge row from OVSDB"""
        for bridge in self.idl.tables["Bridge"].rows.values():
            if bridge.name == bridge_name:
                return bridge
        return None

    def _add_port_to_ovs(
        self, port_name: str, vlan_tag: int = None, bridge_name: str = BRIDGE
    ) -> bool:
        """Add port to OVS bridge via OVSDB IDL (non-blocking)

        For ethernet type interfaces, libvirt only creates the tap device.
        We add the port to OVS ourselves.

        Args:
            port_name: Name of the tap device (e.g., vnet0)
            vlan_tag: Optional VLAN tag for kind="interface"
            bridge_name: OVS bridge name (default: ovsbr0)

        Returns:
            True if successful, False otherwise
        """
        self._run_idl()

        bridge = self._get_bridge(bridge_name)
        if not bridge:
            log(
                {
                    "event": "add_port_error",
                    "port": port_name,
                    "error": f"Bridge {bridge_name} not found",
                }
            )
            return False

        # Check if port already exists
        for port in self.idl.tables["Port"].rows.values():
            if port.name == port_name:
                # Port already exists, just update tag if needed
                if vlan_tag:
                    self._set_port_tag(port_name, vlan_tag)
                return True

        try:
            txn = ovs_idl.Transaction(self.idl)

            # Create Interface row
            iface = txn.insert(self.idl.tables["Interface"])
            iface.name = port_name
            iface.type = ""  # system interface (tap device)

            # Create Port row
            port = txn.insert(self.idl.tables["Port"])
            port.name = port_name
            port.interfaces = [iface]
            if vlan_tag:
                port.tag = vlan_tag

            # Add port to bridge
            bridge.ports = bridge.ports + [port]

            status = txn.commit_block()
            if status not in (
                ovs_idl.Transaction.SUCCESS,
                ovs_idl.Transaction.UNCHANGED,
            ):
                log(
                    {
                        "event": "add_port_error",
                        "port": port_name,
                        "status": str(status),
                    }
                )
                return False

            log(
                {
                    "event": "add_port",
                    "port": port_name,
                    "bridge": bridge_name,
                    "vlan_tag": vlan_tag,
                }
            )
            return True

        except Exception as e:
            log({"event": "add_port_error", "port": port_name, "error": str(e)})
            return False

    def _del_port_from_ovs(self, port_name: str, bridge_name: str = BRIDGE) -> bool:
        """Remove port from OVS bridge via OVSDB IDL (non-blocking)

        Args:
            port_name: Name of the tap device to remove
            bridge_name: OVS bridge name (default: ovsbr0)

        Returns:
            True if successful, False otherwise
        """
        self._run_idl()

        bridge = self._get_bridge(bridge_name)
        if not bridge:
            return True  # Bridge doesn't exist, nothing to do

        try:
            txn = ovs_idl.Transaction(self.idl)

            # Find and remove port
            port_to_delete = None
            for port in bridge.ports:
                if port.name == port_name:
                    port_to_delete = port
                    break

            if not port_to_delete:
                return True  # Port doesn't exist, nothing to do

            # Remove port from bridge
            new_ports = [p for p in bridge.ports if p.name != port_name]
            bridge.ports = new_ports

            # Delete the port and interface rows
            for iface in port_to_delete.interfaces:
                iface.delete()
            port_to_delete.delete()

            status = txn.commit_block()
            if status not in (
                ovs_idl.Transaction.SUCCESS,
                ovs_idl.Transaction.UNCHANGED,
            ):
                log(
                    {
                        "event": "del_port_error",
                        "port": port_name,
                        "status": str(status),
                    }
                )
                return False

            log({"event": "del_port", "port": port_name, "bridge": bridge_name})
            return True

        except Exception as e:
            log({"event": "del_port_error", "port": port_name, "error": str(e)})
            return False

    def _del_ports_batch(self, port_infos: list) -> int:
        """Delete multiple OVS ports in a single OVSDB transaction

        Args:
            port_infos: List of {"port": name, "bridge": bridge_name}

        Returns:
            Number of ports successfully deleted
        """
        if not port_infos:
            return 0

        self._run_idl()

        try:
            txn = ovs_idl.Transaction(self.idl)
            deleted = 0

            for port_info in port_infos:
                port_name = port_info["port"]
                bridge_name = port_info.get("bridge", BRIDGE)

                bridge = self._get_bridge(bridge_name)
                if not bridge:
                    continue

                port_to_delete = None
                for port in bridge.ports:
                    if port.name == port_name:
                        port_to_delete = port
                        break

                if not port_to_delete:
                    continue

                new_ports = [p for p in bridge.ports if p.name != port_name]
                bridge.ports = new_ports

                for iface in port_to_delete.interfaces:
                    iface.delete()
                port_to_delete.delete()
                deleted += 1

            status = txn.commit_block()
            if status in (ovs_idl.Transaction.SUCCESS, ovs_idl.Transaction.UNCHANGED):
                log({"event": "del_ports_batch", "count": deleted})
                return deleted
            else:
                log({"event": "del_ports_batch_error", "status": str(status)})
                return 0

        except Exception as e:
            log({"event": "del_ports_batch_error", "error": str(e)})
            return 0

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

    def _create_meter(self, meter_id: int, rate: int, burst: int):
        """Create a meter for per-VM rate limiting"""
        # Delete first for idempotency (ignore errors if doesn't exist)
        self._ofctl("-O", "OpenFlow13", "del-meter", BRIDGE, f"meter={meter_id}")
        # Create meter with pktps (packets per second)
        self._ofctl(
            "-O",
            "OpenFlow13",
            "add-meter",
            BRIDGE,
            f"meter={meter_id},pktps,burst,bands=type=drop,rate={rate},burst_size={burst}",
        )

    def _create_meters_batch(self, meter_specs: list) -> list:
        """Create multiple meters in a single subprocess call

        Args:
            meter_specs: List of (meter_id, rate, burst) tuples

        Returns:
            List of meter IDs that were created
        """
        if not meter_specs:
            return []

        # Delete existing meters first (single call with all IDs)
        del_ids = [str(spec[0]) for spec in meter_specs]
        for meter_id in del_ids:
            self._ofctl("-O", "OpenFlow13", "del-meter", BRIDGE, f"meter={meter_id}")

        # Build meter definitions
        meter_lines = []
        created_ids = []
        for meter_id, rate, burst in meter_specs:
            meter_lines.append(
                f"meter={meter_id},pktps,burst,bands=type=drop,rate={rate},burst_size={burst}"
            )
            created_ids.append(meter_id)

        # Add meters individually (ovs-ofctl add-meter doesn't support file input)
        for meter_line in meter_lines:
            self._ofctl("-O", "OpenFlow13", "add-meter", BRIDGE, meter_line)

        return created_ids

    def _delete_meters(self, meter_ids: list):
        """Delete multiple meters"""
        for meter_id in meter_ids:
            self._ofctl("-O", "OpenFlow13", "del-meter", BRIDGE, f"meter={meter_id}")

    # =========================================================================
    # Security Stats Collection
    # =========================================================================

    def _build_port_map(self) -> dict:
        """Build ofport -> domain info mapping from in-memory state"""
        port_map = {}
        with self.lock:
            for domain, state in self.domains.items():
                if state.running:
                    for port_info in state.ports:
                        ofport = port_info.get("ofport")
                        if ofport:
                            port_map[ofport] = {
                                "domain": domain,
                                "port": port_info.get("port"),
                                "mac": port_info.get("mac"),
                                "interface_id": port_info.get("interface_id"),
                                "network_id": port_info.get("network_id"),
                            }
        return port_map

    def _parse_blocked_flows(self, output: str, port_map: dict) -> dict:
        """Parse flow stats for blocked traffic by category

        Categories tracked:
        - bpdu: priority=250 (STP manipulation attempts)
        - spoofing: priority=207 (IP spoofing) + priority=197 (MAC spoofing)
        - broadcast: priority=205 with dl_dst=ff:ff:ff:ff:ff:ff
        - multicast: priority=205 with dl_dst=01:00:00:00:00:00
        - ipv6: priority=205 with ipv6
        - ip_blocked: priority=203 (unauthorized IP traffic)
        """
        stats = {
            "bpdu": {},
            "spoofing": {},
            "broadcast": {},
            "multicast": {},
            "ipv6": {},
            "ip_blocked": {},
        }

        for line in output.splitlines():
            m_port = re.search(r"in_port=(\d+)", line)
            m_pkts = re.search(r"n_packets=(\d+)", line)
            if not m_port or not m_pkts:
                continue

            ofport = int(m_port.group(1))
            pkts = int(m_pkts.group(1))
            if pkts == 0:
                continue

            if "priority=250" in line and "01:80:c2:00:00:00" in line:
                stats["bpdu"][ofport] = stats["bpdu"].get(ofport, 0) + pkts
            elif "priority=207" in line:
                stats["spoofing"][ofport] = stats["spoofing"].get(ofport, 0) + pkts
            elif "priority=205" in line:
                if "dl_dst=ff:ff:ff:ff:ff:ff" in line:
                    stats["broadcast"][ofport] = (
                        stats["broadcast"].get(ofport, 0) + pkts
                    )
                elif "dl_dst=01:00:00:00:00:00" in line:
                    stats["multicast"][ofport] = (
                        stats["multicast"].get(ofport, 0) + pkts
                    )
                elif "ipv6" in line:
                    stats["ipv6"][ofport] = stats["ipv6"].get(ofport, 0) + pkts
            elif "priority=203" in line:
                stats["ip_blocked"][ofport] = stats["ip_blocked"].get(ofport, 0) + pkts
            elif "priority=197" in line and "actions=drop" in line:
                stats["spoofing"][ofport] = stats["spoofing"].get(ofport, 0) + pkts

        def top3_with_info(port_stats):
            items = []
            for ofport, pkts in sorted(port_stats.items(), key=lambda x: -x[1])[:3]:
                info = port_map.get(ofport, {})
                entry = {
                    "domain": info.get("domain", "unknown"),
                    "mac": info.get("mac", "unknown"),
                    "port": info.get("port", f"port{ofport}"),
                    "packets": pkts,
                }
                # Add interface name if available
                if info.get("interface_id"):
                    entry["interface"] = info["interface_id"]
                elif info.get("network_id"):
                    entry["network"] = info["network_id"]
                items.append(entry)
            return items

        return {k: top3_with_info(v) for k, v in stats.items()}

    def _parse_meter_stats(self, output: str, port_map: dict) -> list:
        """Parse meter stats for rate-limited traffic

        Meter ID formula: meter_base = 100 + (ofport * 10)
        - meter_base + 0 = ARP (VLAN 4095 only)
        - meter_base + 1 = DHCP (VLAN 4095 only)
        - meter_base + 2 = Broadcast (all VLANs)
        - meter_base + 3 = Multicast (all VLANs)
        """
        stats_by_port = {}

        for block in output.split("meter_id=")[1:]:
            m = re.match(r"(\d+)", block)
            if not m:
                continue

            meter_id = int(m.group(1))
            if meter_id < 100:
                continue

            ofport = (meter_id - 100) // 10
            meter_type_idx = (meter_id - 100) % 10

            meter_types = {0: "arp", 1: "dhcp", 2: "broadcast", 3: "multicast"}
            meter_type = meter_types.get(meter_type_idx)
            if not meter_type:
                continue

            if ofport not in stats_by_port:
                stats_by_port[ofport] = {}

            m_in = re.search(r"packet_in_count=(\d+)", block)
            m_drop = re.search(r"0: packet_count=(\d+)", block)

            stats_by_port[ofport][meter_type] = {
                "in": int(m_in.group(1)) if m_in else 0,
                "dropped": int(m_drop.group(1)) if m_drop else 0,
            }

        # Build top 3 by total dropped
        items = []
        for ofport, stats in stats_by_port.items():
            total_dropped = sum(s.get("dropped", 0) for s in stats.values())
            if total_dropped > 0:
                info = port_map.get(ofport, {})
                entry = {
                    "domain": info.get("domain", "unknown"),
                    "mac": info.get("mac", "unknown"),
                    "port": info.get("port", f"port{ofport}"),
                    "meters": stats,
                    "total_dropped": total_dropped,
                }
                # Add interface name if available
                if info.get("interface_id"):
                    entry["interface"] = info["interface_id"]
                elif info.get("network_id"):
                    entry["network"] = info["network_id"]
                items.append(entry)

        return sorted(items, key=lambda x: -x["total_dropped"])[:3]

    def _parse_rstp_blocked(self, output: str, port_map: dict) -> list:
        """Parse RSTP blocked ports with domain identification"""
        blocked = []

        # Build reverse mapping: port_name -> ofport
        name_to_ofport = {}
        for ofport, info in port_map.items():
            if info.get("port"):
                name_to_ofport[info["port"]] = ofport

        for line in output.splitlines():
            if "Blocking" in line or "Discarding" in line:
                parts = line.split()
                if len(parts) >= 1:
                    port_name = parts[0].strip()
                    state = "Blocking" if "Blocking" in line else "Discarding"
                    ofport = name_to_ofport.get(port_name)
                    info = port_map.get(ofport, {}) if ofport else {}
                    entry = {
                        "port": port_name,
                        "domain": info.get("domain", "unknown"),
                        "mac": info.get("mac", "unknown"),
                        "state": state,
                    }
                    # Add interface name if available
                    if info.get("interface_id"):
                        entry["interface"] = info["interface_id"]
                    elif info.get("network_id"):
                        entry["network"] = info["network_id"]
                    blocked.append(entry)

        return blocked

    def _collect_security_stats(self):
        """Collect and log security stats with domain identification

        Only logs if there's blocked or rate-limited traffic detected.
        """
        port_map = self._build_port_map()
        if not port_map:
            return  # No VMs running

        # Get flow stats
        try:
            result = subprocess.run(
                ["ovs-ofctl", "dump-flows", BRIDGE],
                capture_output=True,
                text=True,
                timeout=5,
            )
            flow_output = result.stdout
        except Exception:
            flow_output = ""

        # Get meter stats
        try:
            result = subprocess.run(
                ["ovs-ofctl", "-O", "OpenFlow13", "meter-stats", BRIDGE],
                capture_output=True,
                text=True,
                timeout=5,
            )
            meter_output = result.stdout
        except Exception:
            meter_output = ""

        # Get RSTP stats
        try:
            result = subprocess.run(
                ["ovs-appctl", "rstp/show", BRIDGE],
                capture_output=True,
                text=True,
                timeout=5,
            )
            rstp_output = result.stdout
        except Exception:
            rstp_output = ""

        # Parse blocked traffic by category
        blocked = self._parse_blocked_flows(flow_output, port_map)

        # Parse rate-limited traffic
        ratelimit = self._parse_meter_stats(meter_output, port_map)

        # Parse RSTP blocked ports
        rstp_blocked = self._parse_rstp_blocked(rstp_output, port_map)

        # Only log if there's blocked/ratelimited traffic
        has_blocked = any(v for v in blocked.values()) or rstp_blocked
        has_ratelimit = any(r.get("total_dropped", 0) > 0 for r in ratelimit)

        if has_blocked or has_ratelimit:
            log(
                {
                    "event": "security_stats",
                    "vms": len(port_map),
                    "rstp_blocked": rstp_blocked,
                    "blocked_top3": {k: v for k, v in blocked.items() if v},
                    "ratelimit_top3": ratelimit,
                }
            )

    def _parse_mac2network_metadata(self, xml_str: str) -> dict:
        """Parse mac2network mappings from XML metadata

        Returns dict mapping MAC address -> network info:
        {
            "52:54:00:aa:bb:01": {
                "kind": "interface",
                "interface_id": "wireguard",
                "vlan_id": 4095,
                "bridge": "ovsbr0"  # optional
            },
            "52:54:00:aa:bb:02": {
                "kind": "user_network",
                "network_id": "uuid-here",
                "metadata_id": 12345
            }
        }
        """
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            log({"event": "xml_parse_error", "error": str(e)})
            return {}

        mappings = {}
        ns = {"isard": "http://isardvdi.com"}

        # Find mac2network in metadata
        for mapping in root.findall(".//{http://isardvdi.com}mapping"):
            mac = mapping.get("mac")
            if not mac:
                continue

            kind = mapping.get("kind", "interface")
            info = {"kind": kind}

            if kind == "interface":
                info["interface_id"] = mapping.get("interface_id", "")
                vlan_id = mapping.get("vlan_id")
                if vlan_id:
                    try:
                        info["vlan_id"] = int(vlan_id)
                    except ValueError:
                        info["vlan_id"] = None
                bridge = mapping.get("bridge")
                if bridge:
                    info["bridge"] = bridge
            elif kind == "user_network":
                info["network_id"] = mapping.get("network_id", "")
                metadata_id = mapping.get("metadata_id")
                if metadata_id:
                    try:
                        info["metadata_id"] = int(metadata_id)
                    except ValueError:
                        info["metadata_id"] = None

            mappings[mac.lower()] = info

        return mappings

    def _parse_interfaces(self, xml_str: str) -> list:
        """Parse interfaces from domain XML

        Handles both:
        - Legacy: type='bridge' with virtualport type='openvswitch'
        - New: type='ethernet' (managed by ovs-worker)
        """
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            log({"event": "xml_parse_error", "error": str(e)})
            return []

        # Parse mac2network metadata first
        mac2network = self._parse_mac2network_metadata(xml_str)

        # Debug: log what we found
        all_ifaces = root.findall(".//interface")
        log(
            {
                "event": "parse_interfaces_debug",
                "total_interfaces": len(all_ifaces),
                "mac2network_count": len(mac2network),
                "mac2network_macs": list(mac2network.keys()),
                "interface_types": [i.get("type") for i in all_ifaces],
            }
        )

        interfaces = []
        for iface in root.findall(".//interface"):
            iface_type = iface.get("type")
            target = iface.find("target")
            mac_elem = iface.find("mac")

            if mac_elem is None:
                continue

            mac = mac_elem.get("address", "").lower()

            # Handle legacy OVS interfaces (type='bridge' with virtualport)
            vport = iface.find("virtualport")
            if vport is not None and vport.get("type") == "openvswitch":
                vlan = iface.find("vlan/tag")
                if target is not None:
                    interfaces.append(
                        {
                            "port": target.get("dev"),
                            "mac": mac,
                            "vlan": vlan.get("id") if vlan is not None else None,
                            "type": "legacy",  # libvirt manages OVS port
                        }
                    )
                continue

            # Handle new ethernet interfaces (managed by ovs-worker)
            if iface_type == "ethernet":
                # For ethernet, libvirt creates tap device but doesn't add to OVS
                # Get network info from mac2network metadata
                network_info = mac2network.get(mac, {})

                # libvirt auto-generates target dev name if not specified
                port_name = target.get("dev") if target is not None else None

                interfaces.append(
                    {
                        "port": port_name,  # May be None until device is created
                        "mac": mac,
                        "vlan": (
                            str(network_info.get("vlan_id"))
                            if network_info.get("vlan_id")
                            else None
                        ),
                        "type": "ethernet",  # ovs-worker manages OVS port
                        "kind": network_info.get("kind", "interface"),
                        "bridge": network_info.get("bridge", BRIDGE),
                        "metadata_id": network_info.get("metadata_id"),
                        "interface_id": network_info.get("interface_id"),
                        "network_id": network_info.get("network_id"),
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
        meter_specs = []  # Collect (meter_id, rate, burst) for batch creation
        ports_managed = []  # Ports we add to OVS (ethernet type)
        vlan4095_count = 0

        for iface in interfaces:
            port = iface["port"]
            mac = iface["mac"]
            vlan = iface["vlan"]
            iface_type = iface.get("type", "legacy")
            kind = iface.get("kind", "interface")
            bridge = iface.get("bridge", BRIDGE)

            if not port or not mac:
                continue

            # For ethernet type interfaces, add port to OVS first
            if iface_type == "ethernet":
                vlan_tag = int(vlan) if vlan and kind == "interface" else None
                if not self._add_port_to_ovs(
                    port, vlan_tag=vlan_tag, bridge_name=bridge
                ):
                    log({"event": "add_port_failed", "port": port, "domain": domain})
                    continue

            # Get OpenFlow port number (with retry for newly added ports)
            nport = self._get_port_ofport(port)
            if not nport:
                log({"event": "port_not_found", "port": port, "domain": domain})
                continue

            # Track port info for cleanup and security stats
            ports_managed.append(
                {
                    "port": port,
                    "bridge": bridge,
                    "mac": mac,
                    "ofport": nport,
                    "type": iface_type,
                    "interface_id": iface.get("interface_id"),
                    "network_id": iface.get("network_id"),
                }
            )

            # ==============================================================
            # Per-VM Meter IDs (base = 100 + ofport * 10)
            # ==============================================================
            meter_base = 100 + (nport * 10)
            meter_arp = meter_base + 0  # VLAN 4095 ARP: 1 pkt/s
            meter_dhcp = meter_base + 1  # VLAN 4095 DHCP: 2 pkt/s
            meter_bcast = meter_base + 2  # Broadcast storm: 10 pkt/s
            meter_mcast = meter_base + 3  # Multicast: 500 pkt/s (video)

            # Collect broadcast/multicast meter specs (all VLANs)
            meter_specs.append((meter_bcast, 10, 50))  # 10 pkt/s, burst 50
            meter_specs.append((meter_mcast, 500, 750))  # 500 pkt/s, burst 750

            # ==============================================================
            # user_network: OpenFlow metadata isolation (skip VLAN flows)
            # ==============================================================
            if kind == "user_network":
                # STP/BPDU protection - ALWAYS apply (even if metadata_id missing)
                flows.append(
                    f"priority=250,in_port={nport},dl_dst=01:80:c2:00:00:00,actions=drop"
                )

                metadata_id = iface.get("metadata_id")
                if metadata_id:
                    # MAC spoofing protection + metadata isolation:
                    # Priority 198 matches correct MAC and sets metadata
                    # Priority 197 drops all other traffic (wrong MAC)
                    flows.append(
                        f"priority=198,in_port={nport},dl_src={mac},"
                        f"actions=set_field:{metadata_id}->metadata,resubmit(,1)"
                    )
                    # Allow traffic within same metadata_id
                    flows.append(
                        f"table=1,priority=100,metadata={metadata_id},dl_dst={mac},actions=output:{nport}"
                    )
                    # Drop all other traffic from this port (wrong MAC or isolation)
                    flows.append(f"priority=197,in_port={nport},actions=drop")

                    # Broadcast/multicast rate limiting for user_network
                    flows.append(
                        f"priority=199,in_port={nport},dl_src={mac},dl_dst=ff:ff:ff:ff:ff:ff,"
                        f"actions=meter:{meter_bcast},set_field:{metadata_id}->metadata,resubmit(,1)"
                    )
                    flows.append(
                        f"priority=199,in_port={nport},dl_src={mac},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,"
                        f"actions=meter:{meter_mcast},set_field:{metadata_id}->metadata,resubmit(,1)"
                    )
                else:
                    # Missing metadata_id - log error and drop all traffic for safety
                    log(
                        {
                            "event": "missing_metadata_id",
                            "port": port,
                            "mac": mac,
                            "domain": domain,
                        }
                    )
                    flows.append(f"priority=197,in_port={nport},actions=drop")

                continue  # Skip VLAN-based flows for user_network

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
            # Priority 199 = above MAC allow (198) to actually rate limit
            # ==============================================================
            # Rate-limit broadcasts (per-VM meter)
            flows.append(
                f"priority=199,in_port={nport},dl_src={mac},dl_dst=ff:ff:ff:ff:ff:ff,actions=meter:{meter_bcast},NORMAL"
            )
            # Rate-limit multicast (per-VM meter, higher rate for video)
            flows.append(
                f"priority=199,in_port={nport},dl_src={mac},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,actions=meter:{meter_mcast},NORMAL"
            )

            # ==============================================================
            # VLAN 4095 Special Handling (Infrastructure Network)
            # ==============================================================
            if vlan == "4095":
                vlan4095_count += 1

                # Collect VLAN 4095 specific meter specs
                meter_specs.append((meter_arp, 1, 10))  # 1 pkt/s, burst 10
                meter_specs.append((meter_dhcp, 2, 5))  # 2 pkt/s, burst 5

                # Set port as access port with VLAN 4095 via OVSDB
                self._set_port_tag(port, 4095)

                # Disable flooding for VLAN 4095 ports (explicit delivery via p221)
                self._ofctl_mod_port(nport, "no-flood")

                # ==== IP SPOOFING PROTECTION ====
                # Block guest from claiming to be infrastructure (10.2.0.0/28)
                flows.append(
                    f"priority=207,arp,in_port={nport},arp_spa=10.2.0.0/28,actions=drop"
                )
                flows.append(
                    f"priority=207,ip,in_port={nport},nw_src=10.2.0.0/28,actions=drop"
                )

                # ARP requests to infrastructure (10.2.0.0/28) - per-VM rate limited
                flows.append(
                    f"priority=206,arp,in_port={nport},dl_src={mac},arp_op=1,arp_tpa=10.2.0.0/28,actions=meter:{meter_arp},NORMAL"
                )
                # ARP replies - per-VM rate limited
                flows.append(
                    f"priority=206,arp,in_port={nport},dl_src={mac},arp_op=2,actions=meter:{meter_arp},NORMAL"
                )

                # DHCP requests from guest - per-VM rate limited
                flows.append(
                    f"priority=206,udp,in_port={nport},dl_src={mac},tp_src=68,tp_dst=67,actions=meter:{meter_dhcp},NORMAL"
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
                    f"priority=205,ipv6,in_port={nport},dl_src={mac},actions=drop"
                )

                # ==== TRAFFIC RESTRICTION ====
                # Allow IP traffic to infrastructure range (10.2.0.0/28)
                flows.append(
                    f"priority=204,ip,in_port={nport},dl_src={mac},nw_dst=10.2.0.0/28,actions=NORMAL"
                )
                # Allow IP traffic to user VPN range (10.0.0.0/16)
                # User-to-desktop access control is handled by iptables in isard-vpn
                flows.append(
                    f"priority=204,ip,in_port={nport},dl_src={mac},nw_dst=10.0.0.0/16,actions=NORMAL"
                )
                # Block all other IP from guest (prevents access to other networks)
                flows.append(
                    f"priority=203,ip,in_port={nport},dl_src={mac},actions=drop"
                )

                # Deliver traffic from VPN to guest - strip VLAN tag before output
                flows.append(
                    f"priority=221,dl_dst={mac},dl_vlan=4095,actions=strip_vlan,output:{nport}"
                )

        # Create all meters in batch (single subprocess call)
        meters = self._create_meters_batch(meter_specs)

        # Apply flows via stdin (no temp file needed)
        if flows:
            cmd = ["ovs-ofctl", "-O", "OpenFlow13", "add-flows", BRIDGE, "-"]
            subprocess.run(
                cmd,
                input=("\n".join(flows) + "\n").encode(),
                check=True,
                capture_output=True,
                timeout=30,
            )

        # Store in memory for cleanup
        with self.lock:
            self.domains[domain].flows = flows
            self.domains[domain].meters = meters
            self.domains[domain].ports = ports_managed
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
                "meters": len(meters),
                "ports": len(ports_managed),
                "duration": now_ms() - start_ms,
            }
        )

    def _flow_del(self, domain: str, count: int = 1):
        """Delete flows for domain using in-memory cache"""
        start_ms = now_ms()

        with self.lock:
            state = self.domains.pop(domain, None)
            if not state:
                return
            flows = state.flows
            meters = state.meters
            ports = state.ports

        if flows:
            # Convert to delete format (remove priority and actions)
            del_matches = []
            for flow in flows:
                match_part = re.sub(r"^priority=\d+,", "", flow)
                match_part = re.sub(r",actions=.*$", "", match_part)
                del_matches.append(match_part)

            self._ofctl_del_flows(del_matches)

        # Clean up per-VM meters
        if meters:
            self._delete_meters(meters)

        # Remove OVS ports we added (ethernet type interfaces only) - batch for performance
        ethernet_ports = [p for p in ports if p.get("type") == "ethernet"]
        if ethernet_ports:
            self._del_ports_batch(ethernet_ports)

        log(
            {
                "event": "flow_del",
                "id": domain,
                "status": "stopped",
                "count": count,
                "queued": self.process_queue.qsize(),
                "flows": len(flows),
                "meters": len(meters),
                "ports": len(ports),
                "duration": now_ms() - start_ms,
            }
        )


def main():
    """Entry point"""
    log(
        {
            "event": "init",
            "socket": SOCKET_PATH,
            "ovsdb": OVSDB_SOCKET,
        }
    )

    worker = OvsWorker()
    worker.start()


if __name__ == "__main__":
    main()
