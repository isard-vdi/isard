# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
"""In-RAM cache of the live libvirt XML of started desktops.

Populated by the hypervisor worker thread when a desktop starts (from the
``XMLDesc(VIR_DOMAIN_XML_SECURE)`` it already reads to learn the assigned
graphics ports) and read by the engine Flask API to serve it on demand to
admins. It is a process-local dict shared across the engine's worker and Flask
threads — it is NEVER written to the database, so the (secret-bearing) live XML
never leaves engine memory.
"""

import threading

_LOCK = threading.Lock()
_CACHE = {}


def set(domain_id, xml):
    """Store the live XML for a started domain (overwrites any previous value)."""
    with _LOCK:
        _CACHE[domain_id] = xml


def get(domain_id):
    """Return the cached live XML for a domain, or None if not cached."""
    with _LOCK:
        return _CACHE.get(domain_id)


def pop(domain_id):
    """Remove and return the cached live XML for a domain (None if absent)."""
    with _LOCK:
        return _CACHE.pop(domain_id, None)
