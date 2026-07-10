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
import ipaddress
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

# Configuration
SOCKET_PATH = "/var/run/openvswitch/ovs-worker.sock"
LOG_FILE = Path("/tmp/qemu-hook.log")
BRIDGE = "ovsbr0"

# Per-interface "lab options" carried on <isard:mapping> as lab_* attributes
# (emitted by the engine, see engine/.../domain_xml.py LAB_OPT_ATTRS). Maps the
# XML attribute name -> the lab_opts key used internally by _flow_add.
LAB_OPT_XML_ATTRS = {
    "lab_mac_spoofing": "mac_spoofing",
    "lab_stp_bpdu": "stp_bpdu",
    "lab_bcast_unlimited": "broadcast_unlimited",
    "lab_mcast_unlimited": "multicast_unlimited",
}

# Meter rates (packets/s, burst). Broadcast/multicast default to tight storm
# protection and are raised to the lab ceiling when the matching lab option is
# enabled — still metered, so a lab storm cannot cross the geneve mesh into
# other hypervisors. The mac_spoofing unicast catch-all is metered to bound a
# rogue lab VM's line-rate abuse (comfortably above heavy GNS3/EVE-NG peaks).
BCAST_DEFAULT_RATE, BCAST_DEFAULT_BURST = 10, 50
MCAST_DEFAULT_RATE, MCAST_DEFAULT_BURST = 500, 750
BCAST_LAB_RATE, BCAST_LAB_BURST = 1000, 2000
MCAST_LAB_RATE, MCAST_LAB_BURST = 5000, 10000
MAC_SPOOF_UNICAST_RATE, MAC_SPOOF_UNICAST_BURST = 10000, 20000

# QEMU/KVM OUI (first three octets) — every IsardVDI desktop NIC is assigned a
# 52:54:00:xx:xx:xx MAC (engine gen_random_mac). In mac_spoofing mode this OUI
# is reserved: only the desktop's own MAC may use it; any other 52:54:00 source
# MAC is dropped so a lab VM cannot impersonate another desktop (FDB poisoning).
KVM_OUI_SRC_MATCH = "52:54:00:00:00:00/ff:ff:ff:00:00:00"

# ---------------------------------------------------------------------------
# BPDU tunneling (stp_bpdu lab option)
# ---------------------------------------------------------------------------
# Guest STP/RSTP/MSTP BPDUs (dst 01:80:c2:00:00:00) are rewritten at ingress to
# an IsardVDI-reserved locally-administered MULTICAST MAC so they traverse the
# VLAN/geneve overlay WITHOUT being consumed by ovsbr0's own RSTP or leaking
# onto a physical trunk (which could err-disable the uplink). They are rewritten
# back to the canonical BPDU MAC before delivery to remote lab guests. The lab
# ports also have port-level RSTP disabled so ovsbr0 does not eat the BPDU
# before the OpenFlow pipeline sees it.
#
# The geneve bucket pushes the VLAN tag explicitly (mod_vlan_vid): raw
# OpenFlow output: actions bypass the OVSDB access-port tagging, which only
# the NORMAL pipeline applies — without the push the remote from-geneve match
# (dl_vlan=N) can never see the frame. Guests are also barred from sourcing
# frames to BPDU_TUNNEL_MAC (per-port priority=250 drop) so the tunnel cannot
# be forged from inside a lab.
#
# !!! LIVE-OVS VALIDATION REQUIRED !!! The remaining OVS semantics this relies
# on (per-port rstp-enable=false, in_port suppression inside type=all groups,
# and that explicit output to a lab tap is not re-consumed by RSTP) must be
# verified on a live two-hypervisor geneve setup with `ovs-appctl ofproto/trace`
# and `ovs-appctl rstp/show` before this option is offered beyond lab use.
BPDU_DST_MAC = "01:80:c2:00:00:00"
# 0x0f first octet: multicast bit (LSB) set + locally-administered bit set;
# NOT in the reserved 01:80:c2:00:00:0x range, unlikely to collide with guests.
BPDU_TUNNEL_MAC = "0f:49:53:41:52:44"  # 0f + "ISARD"
BPDU_TUNNEL_RATE, BPDU_TUNNEL_BURST = 100, 200  # STP control plane is low-rate


def bpdu_group_all(vlan):
    """Group id for the 'guest-originated BPDU' fan-out on a VLAN: local lab
    ports + a geneve bucket. id == vlan (1..4094)."""
    return int(vlan)


def bpdu_group_local(vlan):
    """Group id for the 'BPDU arrived from geneve' fan-out on a VLAN: local lab
    ports only (no geneve bucket -> no tunnel loopback). Disjoint from
    bpdu_group_all()."""
    return 8000 + int(vlan)


def parse_lab_opts(mapping):
    """Read the lab_* attributes from a mac2network mapping dict into a
    {key: bool} dict. Missing attributes default to False (strict). Only the
    exact string "true" (case-insensitive) enables an option — defends against
    stringly-typed values surviving from non-API writers."""
    return {
        key: str(mapping.get(attr, "false")).lower() == "true"
        for attr, key in LAB_OPT_XML_ATTRS.items()
    }


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
    bpdu: list = field(default_factory=list)  # (vlan, ofport) lab-STP tunnel ports
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
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "coalesced": 0,
            "last_elapsed_ms": 0,
        }
        # Security stats collection
        self.last_stats_time = 0
        self.stats_interval = 60  # seconds

        # Compute guest infrastructure CIDR from WG_GUESTS_NETS
        guests_net = ipaddress.ip_network(
            os.environ.get("WG_GUESTS_NETS", "10.2.0.0/16"), strict=False
        )
        self.guests_infra_cidr = str(
            ipaddress.ip_network(f"{guests_net.network_address}/28", strict=False)
        )

        # Discover geneve port number (set up by setup.sh before we start)
        # In wg+geneve mode the interface is named $DOMAIN
        # In geneve mode the interface is named vpn-geneve
        domain = os.environ.get("DOMAIN", "")
        self.geneve_port = None
        for iface_name in [domain, "vpn-geneve"]:
            if not iface_name:
                continue
            try:
                result = subprocess.run(
                    ["ovs-vsctl", "get", "Interface", iface_name, "ofport"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                port = result.stdout.strip()
                if port and port != "-1":
                    self.geneve_port = port
                    log(
                        {
                            "event": "geneve_port_discovered",
                            "port": self.geneve_port,
                            "interface": iface_name,
                        }
                    )
                    break
            except Exception:
                continue

        if self.geneve_port is None:
            log(
                {
                    "event": "geneve_port_error",
                    "error": f"Could not find geneve port via DOMAIN='{domain}' or 'vpn-geneve'",
                }
            )

    def start(self):
        """Initialize and start the worker"""
        self._cleanup_stale_ports()
        self._start_processor_thread()
        self._run_socket_server()

    def _cleanup_stale_ports(self):
        """Remove OVS ports whose underlying device is gone or in error state.

        Stale ports appear when a VM crashes without going through the normal
        stopped-event path.  Must be called before the processor thread starts
        (startup) and periodically from _collect_security_stats.
        """
        try:
            result = subprocess.run(
                ["ovs-vsctl", "list-ports", BRIDGE],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            ports = result.stdout.strip().split("\n") if result.stdout.strip() else []
        except subprocess.CalledProcessError:
            return

        stale = []
        for port_name in ports:
            if not port_name or port_name == BRIDGE:
                continue
            try:
                result = subprocess.run(
                    ["ovs-vsctl", "get", "Interface", port_name, "error", "ofport"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
                lines = result.stdout.strip().split("\n")
                raw_error = lines[0].strip('"') if len(lines) > 0 else ""
                # OVS returns [] for empty optional fields, treat as no error
                error = raw_error if raw_error and raw_error != "[]" else ""
                ofport_str = lines[1].strip() if len(lines) > 1 else "0"
                try:
                    port_num = int(ofport_str)
                except ValueError:
                    port_num = 0
                if error or port_num < 0:
                    stale.append(port_name)
                    log(
                        {
                            "event": "stale_port_found",
                            "port": port_name,
                            "error": error,
                            "ofport": ofport_str,
                        }
                    )
            except subprocess.CalledProcessError:
                continue

        for port_name in stale:
            self._del_port_from_ovs(port_name)
            log({"event": "stale_port_removed", "port": port_name})

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
        """Get OpenFlow port number for a port via ovs-vsctl with retry

        Uses short retries (200ms each) to handle newly added ports.
        Port is added by _add_port_to_ovs() before this is called.
        """
        for attempt in range(retries):
            try:
                # Check for errors first
                result = subprocess.run(
                    ["ovs-vsctl", "get", "Interface", port_name, "error"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
                error = result.stdout.strip().strip('"')
                # OVS returns [] for empty optional fields, treat as no error
                if error and error != "[]":
                    log({"event": "port_error", "port": port_name, "error": error})
                    return None

                result = subprocess.run(
                    ["ovs-vsctl", "get", "Interface", port_name, "ofport"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
                port_num = int(result.stdout.strip())
                if port_num > 0:
                    return port_num
            except (subprocess.CalledProcessError, ValueError):
                pass

            if attempt < retries - 1:
                time.sleep(0.2)

        return None

    def _set_port_tag(self, port_name: str, tag: int):
        """Set VLAN tag on port via ovs-vsctl"""
        try:
            subprocess.run(
                ["ovs-vsctl", "set", "Port", port_name, f"tag={tag}"],
                check=True,
                capture_output=True,
                timeout=5,
            )
        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "set_port_tag_error",
                    "port": port_name,
                    "tag": tag,
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )

    def _bridge_exists(self, bridge_name: str = BRIDGE) -> bool:
        """Check if OVS bridge exists via ovs-vsctl"""
        result = subprocess.run(
            ["ovs-vsctl", "br-exists", bridge_name],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0

    def _add_port_to_ovs(
        self, port_name: str, vlan_tag: int = None, bridge_name: str = BRIDGE
    ) -> bool:
        """Add port to OVS bridge via ovs-vsctl

        For ethernet type interfaces, libvirt only creates the tap device.
        We add the port to OVS ourselves.

        Args:
            port_name: Name of the tap device (e.g., vnet0)
            vlan_tag: Optional VLAN tag for kind="interface"
            bridge_name: OVS bridge name (default: ovsbr0)

        Returns:
            True if successful, False otherwise
        """
        if not self._bridge_exists(bridge_name):
            log(
                {
                    "event": "add_port_error",
                    "port": port_name,
                    "error": f"Bridge {bridge_name} not found",
                }
            )
            return False

        # Check if port already exists on a bridge
        result = subprocess.run(
            ["ovs-vsctl", "port-to-br", port_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Port already exists, just update tag if needed
            if vlan_tag:
                self._set_port_tag(port_name, vlan_tag)
            return True

        try:
            cmd = ["ovs-vsctl", "add-port", bridge_name, port_name]
            if vlan_tag:
                cmd.append(f"tag={vlan_tag}")
            subprocess.run(cmd, check=True, capture_output=True, timeout=5)

            log(
                {
                    "event": "add_port",
                    "port": port_name,
                    "bridge": bridge_name,
                    "vlan_tag": vlan_tag,
                }
            )
            return True

        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "add_port_error",
                    "port": port_name,
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )
            return False

    def _del_port_from_ovs(self, port_name: str, bridge_name: str = BRIDGE) -> bool:
        """Remove port from OVS bridge via ovs-vsctl

        Args:
            port_name: Name of the tap device to remove
            bridge_name: OVS bridge name (default: ovsbr0)

        Returns:
            True if successful, False otherwise
        """
        try:
            subprocess.run(
                ["ovs-vsctl", "--if-exists", "del-port", bridge_name, port_name],
                check=True,
                capture_output=True,
                timeout=5,
            )
            log({"event": "del_port", "port": port_name, "bridge": bridge_name})
            return True
        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "del_port_error",
                    "port": port_name,
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )
            return False

    def _del_ports_batch(self, port_infos: list) -> int:
        """Delete multiple OVS ports in a single ovs-vsctl call

        Args:
            port_infos: List of {"port": name, "bridge": bridge_name}

        Returns:
            Number of ports successfully deleted
        """
        if not port_infos:
            return 0

        cmd = ["ovs-vsctl"]
        for port_info in port_infos:
            port_name = port_info["port"]
            bridge_name = port_info.get("bridge", BRIDGE)
            cmd.extend(["--", "--if-exists", "del-port", bridge_name, port_name])

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
            log({"event": "del_ports_batch", "count": len(port_infos)})
            return len(port_infos)
        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "del_ports_batch_error",
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )
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
    # BPDU tunneling (stp_bpdu lab option) — see module header.
    # LIVE-OVS VALIDATION REQUIRED before use beyond dedicated lab networks.
    # =========================================================================

    def _set_port_rstp_enable(self, port_name: str, enabled: bool):
        """Enable/disable port-level RSTP. Lab-STP ports disable it so guest
        BPDUs reach the OpenFlow pipeline (to be tunneled) instead of being
        consumed by ovsbr0's own RSTP."""
        try:
            subprocess.run(
                [
                    "ovs-vsctl",
                    "set",
                    "Port",
                    port_name,
                    f"other_config:rstp-enable={'true' if enabled else 'false'}",
                ],
                check=True,
                capture_output=True,
                timeout=5,
            )
        except subprocess.CalledProcessError as e:
            log(
                {
                    "event": "set_port_rstp_error",
                    "port": port_name,
                    "error": e.stderr.decode() if e.stderr else str(e),
                }
            )

    def _ovs_replace_group(self, group_id: int, spec: str):
        """Replace an OpenFlow group (delete-then-add) so its bucket set always
        reflects the current union of lab-STP ports on the VLAN."""
        self._ofctl("-O", "OpenFlow13", "del-groups", BRIDGE, f"group_id={group_id}")
        self._ofctl("-O", "OpenFlow13", "add-group", BRIDGE, spec)

    def _sync_bpdu_groups(self, vlans):
        """(Re)build or tear down the BPDU-tunnel groups + from-geneve delivery
        flow for each affected VLAN, from the union of every running domain's
        lab-STP ports. Two groups per VLAN:
          ALL   (id=vlan)      local lab ports (BPDU as-is) + geneve bucket
                               (rewrite to the tunnel MAC) — fan-out for a
                               guest-originated BPDU.
          LOCAL (id=8000+vlan) local lab ports only — fan-out for a BPDU that
                               arrived from geneve (already rewritten back),
                               with no geneve bucket so it cannot loop.
        Callers wrap this so a failure never breaks domain start/stop."""
        for vlan in vlans:
            ofports = sorted(
                {
                    ofport
                    for state in self.domains.values()
                    for (v, ofport) in state.bpdu
                    if v == vlan
                }
            )
            all_gid = bpdu_group_all(vlan)
            local_gid = bpdu_group_local(vlan)
            geneve_from_match = (
                f"in_port={self.geneve_port},dl_dst={BPDU_TUNNEL_MAC},dl_vlan={vlan}"
            )
            # Broader filter (no dl_dst) covers BOTH the priority=251 BPDU
            # rewrite flow above AND the priority=200 from-geneve flood-delivery
            # flow we install below — one teardown match cleans both up.
            geneve_vlan_match = f"in_port={self.geneve_port},dl_vlan={vlan}"
            if not ofports:
                # Last lab-STP port on this VLAN went away: tear it all down.
                self._ofctl(
                    "-O", "OpenFlow13", "del-groups", BRIDGE, f"group_id={all_gid}"
                )
                self._ofctl(
                    "-O", "OpenFlow13", "del-groups", BRIDGE, f"group_id={local_gid}"
                )
                self._ofctl_del_flows([geneve_vlan_match])
                continue
            local_buckets = ",".join(f"bucket=actions=output:{p}" for p in ofports)
            # The geneve bucket egresses via a raw output: action, which does
            # NOT apply the access-port VLAN tag (only NORMAL does) — push the
            # tag explicitly or the remote from-geneve match (dl_vlan=N) can
            # never see the frame. mod_vlan_vid adds the 802.1Q header when
            # the frame is untagged (guest BPDUs always are).
            all_buckets = local_buckets + (
                f",bucket=actions=mod_dl_dst:{BPDU_TUNNEL_MAC},"
                f"mod_vlan_vid:{vlan},output:{self.geneve_port}"
            )
            self._ovs_replace_group(
                all_gid, f"group_id={all_gid},type=all,{all_buckets}"
            )
            self._ovs_replace_group(
                local_gid, f"group_id={local_gid},type=all,{local_buckets}"
            )
            # BPDU arriving from geneve: strip the VLAN tag, rewrite the tunnel
            # MAC back to the canonical BPDU MAC, fan out to local lab ports.
            self._ofctl(
                "-O",
                "OpenFlow13",
                "add-flow",
                BRIDGE,
                f"priority=251,{geneve_from_match},actions=strip_vlan,"
                f"mod_dl_dst:{BPDU_DST_MAC},group:{local_gid}",
            )
            # Non-BPDU from-geneve delivery for this VLAN. With rstp-enable=false
            # on every lab-STP port, OVS NORMAL excludes those ports from its
            # flood domain — so cross-host ARP/broadcast/multicast/unlearned
            # unicast on this VLAN never reaches the lab port without an
            # explicit rule. Reuses local_gid (the type=all group with one
            # bucket per local lab-STP port on this VLAN, already maintained
            # for the BPDU from-geneve path). priority=251 above wins for
            # tunnel-MAC BPDU frames, so they never hit this path. Does NOT
            # fall through to NORMAL: NORMAL would also unicast to a learned
            # lab-STP port (split-horizon excludes the in_port, not the
            # rstp-disabled port), duplicating every learned-MAC frame. Trade-
            # off: a non-stp_bpdu port co-located on the same VLAN won't get
            # from-geneve flood here. A stp_bpdu VLAN is by design a single
            # logical L2 lab segment; mixing strict tenants on the same VLAN
            # is out of scope.
            self._ofctl(
                "-O",
                "OpenFlow13",
                "add-flow",
                BRIDGE,
                f"priority=200,{geneve_vlan_match},"
                f"actions=strip_vlan,group:{local_gid}",
            )

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
        - meter_base + 4 = Unicast catch-all (mac_spoofing lab option only)
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

            meter_types = {
                0: "arp",
                1: "dhcp",
                2: "broadcast",
                3: "multicast",
                4: "unicast",
                5: "bpdu",
            }
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
        self._cleanup_stale_ports()

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
                # Per-interface lab options (see parse_lab_opts). Each enabled
                # flag relaxes one OVS port protection in _flow_add. Wireguard
                # infra (kind="user_network") never carries these — the elif
                # branch below leaves lab_opts unset, so it is always strict.
                info["lab_opts"] = parse_lab_opts(mapping)
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
                        # propagate per-interface lab options so _flow_add
                        # can pick the per-flag flow set.
                        "lab_opts": network_info.get("lab_opts", {}),
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
        bpdu_entries = []  # (vlan:int, ofport) lab-STP tunnel ports for this domain
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
            meter_bcast = meter_base + 2  # Broadcast storm (rate per lab opts)
            meter_mcast = meter_base + 3  # Multicast (rate per lab opts)
            meter_unicast = meter_base + 4  # mac_spoofing unicast catch-all

            # Per-interface lab options (admin webapp, API-validated). Honored
            # only outside VLAN 4095 (wireguard infra) — that VLAN is always
            # strict, so force every flag off there.
            lab = iface.get("lab_opts", {}) if vlan != "4095" else {}
            mac_spoofing = bool(lab.get("mac_spoofing"))
            broadcast_unlimited = bool(lab.get("broadcast_unlimited"))
            multicast_unlimited = bool(lab.get("multicast_unlimited"))
            # lab.get("stp_bpdu") drives BPDU tunneling, added in the
            # dedicated block below (group-based MAC rewrite over the overlay).

            # Broadcast/multicast meters (all VLANs): tight storm protection by
            # default, raised to the lab ceiling when relaxed. Applies in both
            # strict and mac_spoofing modes (the rate flags are independent).
            meter_specs.append(
                (meter_bcast, BCAST_LAB_RATE, BCAST_LAB_BURST)
                if broadcast_unlimited
                else (meter_bcast, BCAST_DEFAULT_RATE, BCAST_DEFAULT_BURST)
            )
            meter_specs.append(
                (meter_mcast, MCAST_LAB_RATE, MCAST_LAB_BURST)
                if multicast_unlimited
                else (meter_mcast, MCAST_DEFAULT_RATE, MCAST_DEFAULT_BURST)
            )

            # ==============================================================
            # user_network: OpenFlow metadata isolation (skip VLAN flows)
            # ==============================================================
            if kind == "user_network":
                # STP/BPDU protection - ALWAYS apply (even if metadata_id missing)
                flows.append(
                    f"priority=250,in_port={nport},dl_dst=01:80:c2:00:00:00,actions=drop"
                )
                # Forged-tunnel-MAC guard: BPDU_TUNNEL_MAC is multicast, so a
                # guest sourcing frames to it would have them flooded over the
                # overlay and reborn as genuine BPDUs by a remote from-geneve
                # rewrite flow. Only the OpenFlow group bucket may ever
                # produce that dst MAC.
                flows.append(
                    f"priority=250,in_port={nport},dl_dst={BPDU_TUNNEL_MAC},actions=drop"
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

                    # Broadcast/multicast rate limiting for user_network.
                    # Broadcast sits strictly ABOVE multicast: ff:ff:.. also
                    # matches the 01:00:../01:00:.. group-bit mask, and
                    # equal-priority overlap is undefined in OpenFlow — the
                    # split guarantees broadcast is accounted to meter_bcast.
                    flows.append(
                        f"priority=200,in_port={nport},dl_src={mac},dl_dst=ff:ff:ff:ff:ff:ff,"
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
            # STP/BPDU Protection (ALL OVS interfaces, ALL modes)
            # ==============================================================
            # Drop STP BPDU frames - prevent spanning tree manipulation
            flows.append(
                f"priority=250,in_port={nport},dl_dst=01:80:c2:00:00:00,actions=drop"
            )
            # Forged-tunnel-MAC guard (ALL modes, incl. stp_bpdu ports — the
            # 251 tunnel ingress only matches the canonical BPDU MAC):
            # BPDU_TUNNEL_MAC is multicast, so a guest sourcing frames to it
            # would have them flooded over geneve and rewritten into genuine
            # BPDUs by the remote from-geneve flow. Only the OpenFlow group
            # bucket may ever produce that dst MAC.
            flows.append(
                f"priority=250,in_port={nport},dl_dst={BPDU_TUNNEL_MAC},actions=drop"
            )

            # ==============================================================
            # MAC Spoofing Protection + Broadcast/Multicast Rate Limiting
            # ==============================================================
            # `mac_spoofing` is a per-interface lab option (admin webapp,
            # API-validated), already forced off above on VLAN 4095.
            if mac_spoofing:
                # Permissive "lab" model:
                #   - No priority=197 catch-all drop and no dl_src gate ->
                #     arbitrary source MACs are accepted (required for nested
                #     L2 setups: GNS3 cloud, EVE-NG, VPCS, bridged nested VMs)
                #     EXCEPT the 52:54:00 KVM OUI, which is reserved to this
                #     desktop's own MAC (see the KVM-OUI guard below) so a lab
                #     VM cannot impersonate another IsardVDI desktop.
                #   - Broadcast/multicast (202): metered + NORMAL + IN_PORT.
                #     IN_PORT delivers the flood back to sibling endpoints that
                #     share this one OVS port (e.g. a GNS3 "cloud" bridging
                #     several sim devices onto one vNIC), which NORMAL's L2
                #     split-horizon would otherwise drop.
                #   - Unicast catch-all (201): metered + NORMAL only, NO
                #     IN_PORT. NORMAL already delivers cross-port unicast to the
                #     correct port; adding IN_PORT would reflect EVERY unicast
                #     back to the sender (self-echo + FDB/MAC-flap inside nested
                #     guest bridges). Same-port unicast hairpin (two endpoints
                #     behind one OVS port unicasting each other through OVS) is
                #     intentionally unsupported — standard nested-lab topologies
                #     switch intra-desktop traffic in the guest's own bridge, so
                #     it never reaches OVS.
                #   NOTE: the unicast meter bounds packet RATE, not the number
                #   of distinct source MACs learned into the shared bridge FDB;
                #   a busy lab VM can still churn the FDB. Acceptable on the
                #   dedicated lab networks this option is restricted to.
                meter_specs.append(
                    (meter_unicast, MAC_SPOOF_UNICAST_RATE, MAC_SPOOF_UNICAST_BURST)
                )
                # KVM-OUI guard: arbitrary source MACs are accepted EXCEPT the
                # 52:54:00 range (KVM_OUI_SRC_MATCH) that every IsardVDI desktop
                # uses — only this desktop's own MAC may use it. Priority layers
                # (per-in_port, so no overlap with the VLAN-4095-only 204-207
                # set on other ports). Broadcast always sits strictly ABOVE its
                # multicast sibling: ff:ff:.. also matches the 01:00:.. group-bit
                # mask and equal-priority overlap is undefined in OpenFlow, so
                # the split guarantees broadcast is accounted to meter_bcast
                # (whose ceiling is raised independently of meter_mcast).
                #   206/205/204  own MAC -> permissive (bcast/mcast/unicast)
                #   203          any other 52:54:00 src -> drop (anti-impersonation)
                #   202/201/200  non-KVM src -> permissive (bcast/mcast/unicast)
                # Own MAC, broadcast: rate-limited + flood + same-port hairpin.
                flows.append(
                    f"priority=206,in_port={nport},dl_src={mac},dl_dst=ff:ff:ff:ff:ff:ff,"
                    f"actions=meter:{meter_bcast},NORMAL,IN_PORT"
                )
                # Own MAC, multicast.
                flows.append(
                    f"priority=205,in_port={nport},dl_src={mac},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,"
                    f"actions=meter:{meter_mcast},NORMAL,IN_PORT"
                )
                # Own MAC, unicast: rate-limited + NORMAL + same-port hairpin.
                # IN_PORT lets the desktop's own stack reach a nested node
                # behind its own OVS port (the D->nested direction of a nested
                # lab such as GNS3/EVE-NG); mirrors the own bcast/mcast above,
                # which already hairpin. NORMAL still delivers the cross-port
                # case (D -> another desktop).
                flows.append(
                    f"priority=204,in_port={nport},dl_src={mac},"
                    f"actions=meter:{meter_unicast},NORMAL,IN_PORT"
                )
                # Block every OTHER 52:54:00 source MAC (cannot impersonate
                # another IsardVDI desktop).
                flows.append(
                    f"priority=203,in_port={nport},dl_src={KVM_OUI_SRC_MATCH},actions=drop"
                )
                # Frames destined TO this desktop's own MAC arriving on its own
                # port (a nested node -> the desktop's own stack, the nested->D
                # direction) must hairpin: NORMAL alone never emits back out the
                # in_port (split-horizon) and D lives on this very port, so only
                # IN_PORT delivers it. Sits BELOW the 203 impersonation drop so a
                # 52:54:00 impostor targeting D is dropped, not hairpinned; the
                # unicast dl_dst is disjoint from the 202 broadcast / 201
                # multicast matches sharing this band.
                flows.append(
                    f"priority=202,in_port={nport},dl_dst={mac},"
                    f"actions=meter:{meter_unicast},IN_PORT"
                )
                # Non-KVM broadcast: rate-limited + flood + same-port hairpin.
                flows.append(
                    f"priority=202,in_port={nport},dl_dst=ff:ff:ff:ff:ff:ff,"
                    f"actions=meter:{meter_bcast},NORMAL,IN_PORT"
                )
                # Non-KVM multicast: rate-limited + flood + same-port hairpin.
                flows.append(
                    f"priority=201,in_port={nport},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,"
                    f"actions=meter:{meter_mcast},NORMAL,IN_PORT"
                )
                # Non-KVM unicast catch-all: rate-limited + NORMAL (no IN_PORT echo).
                flows.append(
                    f"priority=200,in_port={nport},"
                    f"actions=meter:{meter_unicast},NORMAL"
                )
            else:
                # Strict model (default):
                #   - priority=198 allows traffic with the desktop's own MAC
                #   - priority=200 rate-limits broadcast, 199 multicast, from
                #     that same MAC (broadcast strictly above multicast: the
                #     ff:ff:.. address also matches the 01:00:.. group-bit
                #     mask, and equal-priority overlap is undefined in
                #     OpenFlow — the split pins broadcast to meter_bcast)
                #   - priority=197 drops anything else (anti-MAC-spoofing)
                # Allow traffic with correct source MAC -> NORMAL switching
                flows.append(
                    f"priority=198,in_port={nport},dl_src={mac},actions=NORMAL"
                )
                # Rate-limit broadcasts (per-VM meter)
                flows.append(
                    f"priority=200,in_port={nport},dl_src={mac},dl_dst=ff:ff:ff:ff:ff:ff,actions=meter:{meter_bcast},NORMAL"
                )
                # Rate-limit multicast (per-VM meter, higher rate for video)
                flows.append(
                    f"priority=199,in_port={nport},dl_src={mac},dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,actions=meter:{meter_mcast},NORMAL"
                )
                # Drop all other traffic from this port (wrong source MAC)
                flows.append(f"priority=197,in_port={nport},actions=drop")

            # ==============================================================
            # BPDU tunneling (stp_bpdu lab option) — see module header.
            # priority=251 wins over the priority=250 BPDU drop above, so guest
            # BPDUs are tunneled instead of dropped. `lab` is forced empty on
            # VLAN 4095, so this never applies there. The group it targets is
            # (re)built by _sync_bpdu_groups before these flows are installed.
            # ==============================================================
            if lab.get("stp_bpdu"):
                meter_bpdu = meter_base + 5
                meter_specs.append((meter_bpdu, BPDU_TUNNEL_RATE, BPDU_TUNNEL_BURST))
                # Port-level RSTP off so ovsbr0 does not consume the guest BPDU
                # before the OpenFlow pipeline can tunnel it.
                self._set_port_rstp_enable(port, False)
                # Guest BPDU -> meter -> ALL group (local lab ports get it as-is,
                # the geneve bucket rewrites it to the tunnel MAC for the overlay).
                flows.append(
                    f"priority=251,in_port={nport},dl_dst={BPDU_DST_MAC},"
                    f"actions=meter:{meter_bpdu},group:{bpdu_group_all(int(vlan))}"
                )
                bpdu_entries.append((int(vlan), nport))

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
                # Block guest from claiming to be infrastructure
                flows.append(
                    f"priority=207,arp,in_port={nport},arp_spa={self.guests_infra_cidr},actions=drop"
                )
                flows.append(
                    f"priority=207,ip,in_port={nport},nw_src={self.guests_infra_cidr},actions=drop"
                )

                # ARP requests to infrastructure - per-VM rate limited
                flows.append(
                    f"priority=206,arp,in_port={nport},dl_src={mac},arp_sha={mac},arp_op=1,arp_tpa={self.guests_infra_cidr},actions=meter:{meter_arp},NORMAL"
                )
                # ARP replies - per-VM rate limited
                flows.append(
                    f"priority=206,arp,in_port={nport},dl_src={mac},arp_sha={mac},arp_op=2,actions=meter:{meter_arp},NORMAL"
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
                # Allow all IP traffic from guest with correct MAC
                # Destination access control is enforced by iptables FORWARD
                # (default DROP + per-desktop ACCEPT) in isard-vpn container
                flows.append(
                    f"priority=204,ip,in_port={nport},dl_src={mac},actions=NORMAL"
                )

                # Deliver traffic from VPN to guest - strip VLAN tag before output
                # Only accept from geneve tunnel to prevent same-hypervisor VM bypass
                if self.geneve_port:
                    flows.append(
                        f"priority=221,in_port={self.geneve_port},dl_dst={mac},dl_vlan=4095,actions=strip_vlan,output:{nport}"
                    )
                else:
                    flows.append(
                        f"priority=221,dl_dst={mac},dl_vlan=4095,actions=strip_vlan,output:{nport}"
                    )

        # Create all meters in batch (single subprocess call)
        meters = self._create_meters_batch(meter_specs)

        # BPDU tunneling: register this domain's lab-STP ports and (re)build the
        # per-VLAN groups BEFORE the flows below reference them (group:<id>).
        # Guarded so a failure here never aborts a normal domain start.
        if bpdu_entries:
            try:
                with self.lock:
                    self.domains[domain].bpdu = bpdu_entries
                self._sync_bpdu_groups({v for v, _ in bpdu_entries})
            except Exception as e:
                log({"event": "bpdu_sync_error", "id": domain, "error": str(e)})

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
            bpdu = state.bpdu

        # BPDU tunneling: rebuild/tear down the per-VLAN groups now that this
        # domain (already popped above) no longer contributes its lab-STP ports.
        # Guarded so a failure never breaks normal teardown.
        if bpdu:
            try:
                self._sync_bpdu_groups({v for v, _ in bpdu})
            except Exception as e:
                log({"event": "bpdu_sync_error", "id": domain, "error": str(e)})

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
        }
    )

    worker = OvsWorker()
    worker.start()


if __name__ == "__main__":
    main()
