"""Python bindings for WireGuard."""

from __future__ import annotations
from ipaddress import ip_network
from os import linesep
from pathlib import Path
from subprocess import check_call, check_output
from typing import NamedTuple


__all__ = [
    'WG',
    'Keypair',
    'genkey',
    'pubkey',
    'keypair',
    'genpsk',
    'show',
    'set',
    'clear_peers'
]


WG = '/usr/bin/wg'


class Keypair(NamedTuple):
    """A public / private key pair."""

    public: str
    private: str

    @classmethod
    def generate(cls, private: str = None, *, _wg: str = WG) -> Keypair:
        """Generates a public / private key pair."""
        if private is None:
            private = genkey(_wg=_wg)

        public = pubkey(private, _wg=_wg)
        return Keypair(public, private)


def genkey(*, _wg: str = WG) -> str:
    """Generates a new private key."""

    return check_output((_wg, 'genkey'), text=True).strip()


def pubkey(key: str, *, _wg: str = WG) -> str:
    """Generates a public key for the given private key."""

    return check_output((_wg, 'pubkey'), input=key, text=True).strip()


def keypair(*, _wg: str = WG) -> Keypair:
    """Generates a public-private key pair."""

    return Keypair.generate(_wg=_wg)


def genpsk(*, _wg: str = WG) -> str:
    """Generates a pre-shared key."""

    return check_output((_wg, 'genpsk'), text=True).strip()


def _parse_ip_networks(value: str, json: bool = False):
    """Returns a parsed IP networks from a string."""

    for network in value.split(','):
        network = network.strip()

        if network == '(none)':
            continue

        if not json:
            network = ip_network(network)

        yield network


def parse_value(key: str, value: str, json: bool = False):
    """Parses key / value pairs for wg show."""

    if key == 'allowed ips':
        return list(_parse_ip_networks(value, json=json))

    if key == 'listening port':
        return int(value)

    if key == 'transfer':
        received, sent = value.split(',')
        return {
            'received': received.replace('received', '').strip(),
            'sent': sent.replace('sent', '').strip()
        }

    if value == '(hidden)':
        return None

    return value


def parse_interface(text: str, raw: bool = False, json: bool = False) -> dict:
    """Parses interface information from the given text."""

    interface = {'peers': {}}
    peer = None

    for line in text.split(linesep):
        if not (line := line.strip()):
            continue

        key, value = line.split(': ')

        if not raw:
            value = parse_value(key, value, json=json)

        if key == 'peer':
            interface['peers'][value] = peer = {}
            continue

        if peer is None:
            interface[key] = value
        else:
            peer[key] = value

    return interface


def parse_interfaces(text: str, raw: bool = False, json: bool = False) -> dict:
    """parses interface information from
    the given text for multiple interfaces.
    """

    interfaces = {}
    interface = {}
    peer = None

    for line in text.split(linesep):
        if not (line := line.strip()):
            continue

        key, value = line.split(': ')

        if not raw:
            value = parse_value(key, value, json=json)

        if key == 'interface':
            interfaces[value] = interface = {'peers': {}}
            peer = None
            continue

        if key == 'peer':
            interface['peers'][value] = peer = {}
            continue

        if peer is None:
            interface[key] = value
        else:
            peer[key] = value

    return interfaces


def show(interface: str = 'all', *, raw: bool = False,
         json: bool = False, _wg: str = WG):
    """Yields status information."""

    if interface == 'all':
        text = check_output((_wg, 'show', 'all'), text=True).strip()
        return parse_interfaces(text, raw=raw, json=json)

    if interface == 'interfaces':
        text = check_output((_wg, 'show', 'interfaces'), text=True).strip()
        return text.split()

    text = check_output((_wg, 'show', interface), text=True).strip()
    return parse_interface(text, raw=raw, json=json)


# pylint: disable=W0622
def set(interface: str, listen_port: int = None, fwmark: str = None,
        private_key: Path = None, peers: dict = None, *, _wg: str = WG):
    """Sets interface configuration."""

    args = ['set', interface]

    if listen_port is not None:
        args.append('listen-port')
        args.append(str(listen_port))

    if fwmark is not None:
        args.append('fwmark')
        args.append(fwmark)

    if private_key is not None:
        args.append('private-key')
        args.append(private_key)

    if peers:
        for peer, settings in peers.items():
            args.append('peer')
            args.append(peer)

            if settings.get('remove'):
                args.append('remove')

            if psk := settings.get('preshared-key'):
                args.append('preshared-key')
                args.append(psk)

            if endpoint := settings.get('endpoint'):
                args.append('endpoint')
                args.append(str(endpoint))

            if persistent_keepalive := settings.get('persistent-keepalive'):
                args.append('persistent-keepalive')
                args.append(str(persistent_keepalive))

            if allowed_ips := settings.get('allowed-ips'):
                args.append('allowed-ips')
                args.append(','.join(str(ip) for ip in allowed_ips))

    return check_call((_wg, *args))


def clear_peers(interface: str, *, _wg: str = WG):
    """Removes all peers from the selected interface or all interfaces."""

    if interface == 'interfaces':
        raise ValueError('Invalid interface name:', interface)

    if interface == 'all':
        for interface in show('interfaces', _wg=_wg):  # pylint: disable=R1704
            clear_peers(interface, _wg=_wg)
    else:
        peers = show(interface, _wg=_wg)['peers'].keys()
        peers = {key: {'remove': True} for key in peers}

        if peers:
            set(interface, peers=peers, _wg=_wg)
