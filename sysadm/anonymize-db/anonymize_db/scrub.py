"""Per-table scrubbers + a defensive recursive sweep.

Operates on already-parsed JSON (lists of dicts loaded from
`<dump>/<db>/<table>.json`). Returns the scrubbed list and a count of
fields touched (for `--dry-run` reporting).
"""

from __future__ import annotations

import base64
import logging
import re
import secrets
from collections.abc import Callable
from functools import partial
from typing import Any

import bcrypt
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from faker import Faker

log = logging.getLogger(__name__)

# Built-in admin must stay loginable in dev with a known password.
ADMIN_ID = "local-default-admin-admin"
DEFAULT_USER_PASSWORD = "pirineus"  # all users (incl. admin) get this in dev
ADMIN_DEV_PASSWORD = DEFAULT_USER_PASSWORD

# Default guest_properties.credentials kept verbatim (matches the well-known
# IsardVDI demo VM credentials so dev viewers still work out of the box).
GUEST_DEFAULT_USERNAME = "isard"
GUEST_DEFAULT_PASSWORD = "pirineus"

# Keys whose value is sensitive when found anywhere in the tree.
# Excluded names are FK-like ids and a few known non-sensitive keys.
_SENSITIVE_KEY_RE = re.compile(
    r"^(?:password|passwd|secret|client_secret|api_key|api-key|"
    r"private_key|access_key|secret_key|bearer|auth_token|access_token)$",
    re.IGNORECASE,
)
_EXCLUDED_TOKEN_KEYS = {
    "email_verification_token",  # already handled in users scrubber
    "password_reset_token",  # already handled in users scrubber
    "password_history",  # handled in users scrubber
    "password_last_updated",  # timestamp, not a secret
}


class IdRemap:
    """Records old→new value rewrites so a final cross-table pass can fix
    any other table that stored the old value (referential consistency).

    Namespaces are closed value sets (e.g. user.uid, category.uid). A leaf
    string equal to a known old value is replaced with its mapped new value.
    Lookup checks namespaces in insertion order; first hit wins.
    """

    def __init__(self):
        self.maps: dict[str, dict[str, str]] = {}

    # Minimum length for a value to be eligible for cross-table rewriting.
    # Short strings (e.g. "admin", "iso", "ide", "default") collide with
    # catalog table primary keys; never register them.
    MIN_REMAP_LEN = 12

    def remap(self, namespace: str, old: str, new: str) -> str:
        if (
            isinstance(old, str)
            and old
            and old != new
            and len(old) >= self.MIN_REMAP_LEN
        ):
            self.maps.setdefault(namespace, {})[old] = new
        return new

    def lookup(self, value: str) -> str | None:
        for m in self.maps.values():
            if value in m:
                return m[value]
        return None


class Scrubber:
    """Holds the deterministic state used by all scrubbers."""

    def __init__(self, seed: int = 0):
        self.faker = Faker()
        self.faker.seed_instance(seed)
        self._bcrypt_cache: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self.remap = IdRemap()

    # ---- helpers ----
    def _bump(self, table: str, n: int = 1) -> None:
        self.counts[table] = self.counts.get(table, 0) + n

    def _bcrypt(self, plaintext: str) -> str:
        if plaintext not in self._bcrypt_cache:
            self._bcrypt_cache[plaintext] = bcrypt.hashpw(
                plaintext.encode(), bcrypt.gensalt(rounds=10)
            ).decode()
        return self._bcrypt_cache[plaintext]

    @staticmethod
    def _wg_keypair() -> tuple[str, str]:
        priv = X25519PrivateKey.generate()
        priv_raw = priv.private_bytes_raw()
        pub_raw = priv.public_key().public_bytes_raw()
        return (
            base64.b64encode(priv_raw).decode(),
            base64.b64encode(pub_raw).decode(),
        )

    @staticmethod
    def _fake_mac(idx: int) -> str:
        # locally-administered, unicast (02:..); deterministic per idx
        rng = secrets.token_bytes(5) if idx < 0 else None
        if rng is None:
            b = idx.to_bytes(5, "big", signed=False)
        else:
            b = rng
        return "02:" + ":".join(f"{x:02x}" for x in b)

    # ---- defensive sweep ----
    def defensive_sweep(self, table: str, obj: Any, _path: tuple[str, ...] = ()) -> Any:
        if isinstance(obj, dict):
            # Special case: leave guest_properties.credentials untouched here.
            # The per-table scrubber for `domains` rewrites it to a known
            # default (isard / pirineus) so dev viewers work out of the box.
            if (
                _path
                and _path[-1] == "credentials"
                and len(_path) >= 2
                and _path[-2] == "guest_properties"
            ):
                return obj
            for k, v in list(obj.items()):
                if (
                    isinstance(k, str)
                    and k not in _EXCLUDED_TOKEN_KEYS
                    and _SENSITIVE_KEY_RE.match(k)
                    and isinstance(v, (str, bytes))
                    and v not in ("", None)
                ):
                    # Replace with a fresh non-empty token so consumers that
                    # check truthiness still see a populated field, but the
                    # value bears no relation to the original secret.
                    obj[k] = f"anon-{secrets.token_urlsafe(12)}"
                    self._bump(table)
                else:
                    obj[k] = self.defensive_sweep(table, v, _path + (k,))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = self.defensive_sweep(table, v, _path)
        return obj

    # ---- per-table scrubbers ----
    def _scrub_wireguard(self, vpn_block: Any) -> None:
        """Scrub a wireguard sub-tree wherever it appears.

        Regenerates keypair, blanks Address / endpoint / remote_ip /
        remote_port. Safe to call on missing/partial blocks.
        """
        if not isinstance(vpn_block, dict):
            return
        wg = vpn_block.get("wireguard")
        if not isinstance(wg, dict):
            return
        if isinstance(wg.get("keys"), dict):
            priv, pub = self._wg_keypair()
            wg["keys"]["private"] = priv
            wg["keys"]["public"] = pub
        for k in ("Address", "address", "endpoint", "remote_ip", "remote_port"):
            if k in wg:
                wg[k] = None

    def users(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            uid = r.get("id", "")
            short = uid[:8] if uid else self.faker.pystr(8, 8)
            if uid == ADMIN_ID:
                r["password"] = self._bcrypt(ADMIN_DEV_PASSWORD)
            else:
                r["password"] = self._bcrypt(DEFAULT_USER_PASSWORD)
                # email, name, username and uid are all registered for the
                # final cross-table rewrite pass, so anywhere IsardVDI
                # denormalizes them by value (e.g. domains.username, owner_*
                # snapshots, the user_storage sub-doc) receives the SAME
                # replacement. IdRemap only registers values >= MIN_REMAP_LEN
                # (12) and the rewrite replaces whole string leaves only, so
                # short catalog ids (e.g. roles.id "advanced") cannot collide.
                old_email = r.get("email")
                r["email"] = self.remap.remap(
                    "user.email",
                    old_email if isinstance(old_email, str) else "",
                    f"user-{short}@example.test",
                )
                old_name = r.get("name")
                r["name"] = self.remap.remap(
                    "user.name",
                    old_name if isinstance(old_name, str) else "",
                    self.faker.name(),
                )
                r["photo"] = ""
                if isinstance(r.get("username"), str):
                    r["username"] = self.remap.remap(
                        "user.username", r["username"], f"user-{short}"
                    )
                if isinstance(r.get("uid"), str):
                    r["uid"] = self.remap.remap("user.uid", r["uid"], f"user-{short}")
            r["password_history"] = []
            r["password_reset_token"] = ""
            r["email_verification_token"] = ""
            r["email_verified"] = True
            r["api_key"] = ""
            r["accessed"] = 0
            # Admin-authored free-text note about the person.
            if isinstance(r.get("description"), str):
                r["description"] = ""
            # The user_storage sub-doc (Nextcloud sync) mirrors the user's
            # email and real name (displayname). Re-point them at the already
            # scrubbed values so no PII survives and they stay consistent with
            # the top-level fields. `password`/`quota` here are handled by the
            # defensive sweep / left untouched respectively.
            us = r.get("user_storage")
            if isinstance(us, dict):
                if isinstance(us.get("email"), str) and isinstance(r.get("email"), str):
                    us["email"] = r["email"]
                if isinstance(us.get("displayname"), str) and isinstance(
                    r.get("name"), str
                ):
                    us["displayname"] = r["name"]
            self._scrub_wireguard(r.get("vpn"))
            self._bump("users")
        return rows

    def _scrub_domain(self, r: dict, i: int) -> None:
        """Scrub one domain object in place. Reused for embedded domain
        snapshots — e.g. storage.last_domain_attached, which is a full domain
        carrying the owner username/email, name, viewer secrets, guest creds
        and libvirt xml."""
        from .xml_scrub import scrub_libvirt_xml

        uid = r.get("id", "")
        short = uid[:8] if uid else f"{i}"
        r["name"] = f"desktop-{short}"
        r["description"] = ""
        r["hyp_started"] = False
        r["history_domain"] = []
        # Denormalized owner username: derive from the `user` FK so it
        # equals the owner's scrubbed users.username (user-<user_id8>),
        # NOT the domain id. Falls back to the domain id only if the FK
        # is missing.
        if isinstance(r.get("username"), str):
            owner = r.get("user")
            owner8 = owner[:8] if isinstance(owner, str) and owner else short
            r["username"] = f"user-{owner8}"
        if isinstance(r.get("tag_name"), str):
            r["tag_name"] = ""
        if isinstance(r.get("tag"), str):
            r["tag"] = ""
        if isinstance(r.get("jumperurl"), str):
            r["jumperurl"] = secrets.token_urlsafe(16)
        cd = r.get("create_dict")
        for sub in cd if isinstance(cd, list) else [cd]:
            if not isinstance(sub, dict):
                continue
            if isinstance(sub.get("name"), str):
                sub["name"] = r["name"]
            if isinstance(sub.get("description"), str):
                sub["description"] = ""
            hw = sub.get("hardware") or {}
            if isinstance(hw, dict):
                for snap_key in ("interfaces", "isos", "floppies"):
                    snap = hw.get(snap_key)
                    if isinstance(snap, list):
                        for s in snap:
                            if not isinstance(s, dict):
                                continue
                            if isinstance(s.get("name"), str):
                                s["name"] = ""
                            if isinstance(s.get("description"), str):
                                s["description"] = ""
        # `hardware` block at the top level mirrors create_dict.hardware
        hw = r.get("hardware")
        if isinstance(hw, dict):
            for snap_key in ("interfaces", "isos", "floppies"):
                snap = hw.get(snap_key)
                if isinstance(snap, list):
                    for s in snap:
                        if not isinstance(s, dict):
                            continue
                        if isinstance(s.get("name"), str):
                            s["name"] = ""
                        if isinstance(s.get("description"), str):
                            s["description"] = ""
        v = r.get("viewer")
        if isinstance(v, dict):
            for k in list(v.keys()):
                if k in {
                    "guest_ip",
                    "session_id",
                    "passwd",
                    "ticket",
                    "tls_port",
                    "port",
                }:
                    v[k] = None
            tls = v.get("tls")
            if isinstance(tls, dict):
                for k in ("certificate", "server-cert", "host-subject", "key"):
                    if k in tls:
                        tls[k] = ""
        gp = r.get("guest_properties") or {}
        if isinstance(gp.get("credentials"), dict):
            gp["credentials"] = {
                "username": GUEST_DEFAULT_USERNAME,
                "password": GUEST_DEFAULT_PASSWORD,
            }
        # Bastion SSH config: each authorized_key's comment is typically the
        # owner's email (ssh-ed25519 AAAA... user@host).
        ssh = r.get("ssh")
        if isinstance(ssh, dict) and isinstance(ssh.get("authorized_keys"), list):
            ssh["authorized_keys"] = []
        cd = r.get("create_dict") or {}
        hw = cd.get("hardware") or {}
        ifs = hw.get("interfaces")
        if isinstance(ifs, list):
            for j, ifc in enumerate(ifs):
                if isinstance(ifc, dict) and "mac" in ifc:
                    ifc["mac"] = self._fake_mac(i * 100 + j)
        xml = r.get("xml")
        if isinstance(xml, str) and xml:
            r["xml"] = scrub_libvirt_xml(xml)

    def domains(self, rows: list[dict]) -> list[dict]:
        for i, r in enumerate(rows):
            self._scrub_domain(r, i)
            self._bump("domains")
        return rows

    def storage(self, rows: list[dict]) -> list[dict]:
        # Storage paths / ids / qemu-img-info are NOT PII and stay intact. The
        # one PII carrier is the embedded `last_domain_attached` — a full domain
        # snapshot with the owner username/email, name, viewer secrets, guest
        # creds and xml — so scrub it exactly like a live domain. This also
        # covers orphaned storage of DELETED users (whose identity was never
        # registered for the cross-table rewrite).
        for i, r in enumerate(rows):
            lda = r.get("last_domain_attached")
            if isinstance(lda, dict):
                self._scrub_domain(lda, i)
            self._bump("storage")
        return rows

    def usage_consumption(self, rows: list[dict]) -> list[dict]:
        # `item_name` denormalizes the consumed item's name; for user/desktop
        # items that is the owner email or login (PII), and it survives for
        # deleted users. Rebuild it from the non-PII item_type + item_id.
        for r in rows:
            if isinstance(r.get("item_name"), str):
                it = r.get("item_type") or "item"
                iid = r.get("item_id")
                r["item_name"] = (
                    f"{it}-{iid[:8]}" if isinstance(iid, str) and iid else ""
                )
            self._bump("usage_consumption")
        return rows

    def _drop_table(self, name: str, rows: list[dict]) -> list[dict]:
        n = len(rows)
        if n:
            self._bump(name, n)
        return []

    def hypervisors(self, rows):
        # Hostnames, VPN endpoints, hardware identifiers all leak site
        # topology. Local dev recreates them on first `isard-engine` boot.
        return self._drop_table("hypervisors", rows)

    def vgpus(self, rows):
        # Discovered vGPU devices, tied to a real hypervisor. Drop.
        return self._drop_table("vgpus", rows)

    def gpus(self, rows):
        # Auto-discovered physical GPUs (id prefix `auto-`). Drop.
        return self._drop_table("gpus", rows)

    def engine(self, rows):
        # Runtime thread state referencing real hypervisor names.
        return self._drop_table("engine", rows)

    def hypervisors_pools(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            v = r.get("viewer")
            if isinstance(v, dict):
                for k in ("certificate", "server-cert", "host-subject"):
                    if k in v:
                        v[k] = ""
            self._bump("hypervisors_pools")
        return rows

    def targets(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            ssh = r.get("ssh")
            if isinstance(ssh, dict) and "authorized_keys" in ssh:
                ssh["authorized_keys"] = []
            self._bump("targets")
        return rows

    def secrets(self, rows: list[dict]) -> list[dict]:
        n = len(rows)
        if n:
            self._bump("secrets", n)
        return []

    def remotevpn(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            rid = r.get("id", "")
            short = rid[:8] if rid else self.faker.pystr(8, 8)
            if isinstance(r.get("name"), str):
                r["name"] = f"vpn-{short}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            self._scrub_wireguard(r.get("vpn"))
            self._bump("remotevpn")
        return rows

    def media(self, rows: list[dict]) -> list[dict]:
        for i, r in enumerate(rows):
            mid = r.get("id", "")
            short = mid[:8] if mid else f"{i}"
            r["url-web"] = ""
            r["url-isard"] = False
            if isinstance(r.get("name"), str):
                r["name"] = f"media-{short}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            if isinstance(r.get("path"), str):
                r["path"] = f"anon/{short}"
            if isinstance(r.get("path_downloaded"), str):
                new_pd = f"/isard/media/{mid}" if mid else ""
                r["path_downloaded"] = self.remap.remap(
                    "media.path_downloaded", r["path_downloaded"], new_pd
                )
            if isinstance(r.get("username"), str):
                r["username"] = "admin"
            self._bump("media")
        return rows

    @staticmethod
    def _blank_email_domain_restrictions(obj: Any) -> None:
        """Rewrite every `email_domain_restriction.allowed` list found anywhere
        in the tree (real path is authentication.{ldap,saml,...}.
        email_domain_restriction.allowed) — those allowed SSO domains identify
        the customer organisation."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if (
                    k == "email_domain_restriction"
                    and isinstance(v, dict)
                    and isinstance(v.get("allowed"), list)
                ):
                    v["allowed"] = ["example.test"] if v["allowed"] else []
                else:
                    Scrubber._blank_email_domain_restrictions(v)
        elif isinstance(obj, list):
            for v in obj:
                Scrubber._blank_email_domain_restrictions(v)

    def categories(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            cid = r.get("id", "") or self.faker.pystr(8, 8)
            # Allowed SSO/registration email domains identify the customer org.
            # Applies to the default category too (before the early-continue).
            self._blank_email_domain_restrictions(r)
            if cid == "default":
                # built-in default category: names public, but its uid may
                # still hold an SSO-mapped value (e.g. `Isard_Admins`).
                if isinstance(r.get("uid"), str):
                    r["uid"] = self.remap.remap("category.uid", r["uid"], cid)
                continue
            if isinstance(r.get("name"), str):
                r["name"] = f"category-{cid}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            if isinstance(r.get("custom_url_name"), str):
                r["custom_url_name"] = cid
            if isinstance(r.get("uid"), str):
                r["uid"] = self.remap.remap("category.uid", r["uid"], cid)
            br = r.get("branding") or {}
            dom = br.get("domain") if isinstance(br, dict) else None
            if isinstance(dom, dict) and isinstance(dom.get("name"), str):
                dom["name"] = ""
            self._bump("categories")
        return rows

    def groups(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            gid = r.get("id", "") or self.faker.pystr(8, 8)
            if isinstance(r.get("name"), str):
                r["name"] = f"group-{gid[:12]}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            if isinstance(r.get("uid"), str):
                r["uid"] = self.remap.remap("group.uid", r["uid"], gid)
            self._bump("groups")
        return rows

    def deployments(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            did = r.get("id", "") or self.faker.pystr(8, 8)
            short = did[:8]
            if isinstance(r.get("name"), str):
                r["name"] = f"deployment-{short}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            if isinstance(r.get("tag_name"), str):
                r["tag_name"] = ""
            if isinstance(r.get("tag"), str):
                r["tag"] = ""
            cd = r.get("create_dict")
            for sub in cd if isinstance(cd, list) else [cd]:
                if not isinstance(sub, dict):
                    continue
                if isinstance(sub.get("name"), str):
                    sub["name"] = f"deployment-{short}"
                if isinstance(sub.get("description"), str):
                    sub["description"] = ""
                if isinstance(sub.get("tag"), str):
                    sub["tag"] = ""
                gp = sub.get("guest_properties")
                if isinstance(gp, dict) and isinstance(gp.get("credentials"), dict):
                    gp["credentials"] = {
                        "username": GUEST_DEFAULT_USERNAME,
                        "password": GUEST_DEFAULT_PASSWORD,
                    }
            self._bump("deployments")
        return rows

    def notifications_data(self, rows: list[dict]) -> list[dict]:
        # `vars` carries snapshotted user-content (desktop names, emails, urls).
        for r in rows:
            v = r.get("vars")
            if isinstance(v, dict):
                for k in list(v.keys()):
                    if isinstance(v[k], str) and any(
                        tok in k.lower()
                        for tok in ("name", "email", "url", "description", "title")
                    ):
                        v[k] = ""
            self._bump("notifications_data")
        return rows

    def bookings(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            if isinstance(r.get("title"), str):
                r["title"] = ""
            self._bump("bookings")
        return rows

    def interfaces(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            iid = r.get("id", "") or self.faker.pystr(8, 8)
            if isinstance(r.get("name"), str):
                r["name"] = f"iface-{iid[:12]}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            self._bump("interfaces")
        return rows

    def vouchers(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            if "code" in r:
                r["code"] = secrets.token_urlsafe(16)
            self._bump("vouchers")
        return rows

    def users_migrations(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            if "token" in r:
                r["token"] = secrets.token_urlsafe(32)
            self._bump("users_migrations")
        return rows

    # Keys whose string values get blanked anywhere in recycle_bin nested trees.
    # `(?:^|_)uid$` catches the SSO `uid` (== email for many installs) in deleted
    # user/domain snapshots without matching `uuid`.
    _RB_BLANK_RE = re.compile(
        r"name|description|email|username|ip|hostname|jumperurl|"
        r"title|comment|certificate|server-cert|host-subject|password_history|"
        r"authorized_keys|(?:^|_)uid$",
        re.I,
    )

    def _recycle_walk(self, obj: Any, path: tuple[str, ...] = ()) -> Any:
        if isinstance(obj, dict):
            # WireGuard sub-trees: regenerate keys + blank addresses.
            if "wireguard" in obj and isinstance(obj.get("wireguard"), dict):
                self._scrub_wireguard(obj)
            # Domain-style guest_properties.credentials → demo creds.
            if (
                path
                and path[-1] == "credentials"
                and len(path) >= 2
                and path[-2] == "guest_properties"
            ):
                obj["username"] = GUEST_DEFAULT_USERNAME
                obj["password"] = GUEST_DEFAULT_PASSWORD
                return obj
            for k, v in list(obj.items()):
                if (
                    isinstance(k, str)
                    and self._RB_BLANK_RE.search(k)
                    and isinstance(v, (str, list))
                ):
                    obj[k] = "" if isinstance(v, str) else []
                else:
                    obj[k] = self._recycle_walk(v, path + (k,))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = self._recycle_walk(v, path)
        return obj

    def recycle_bin(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            self._recycle_walk(r)
            self._bump("recycle_bin")
        return rows

    def logs_users(self, rows: list[dict]) -> list[dict]:
        # Keep rows for realistic dev/analytics volume; blank PII fields.
        # FK-like *_id fields stay so joins still work; the cross-table
        # rewrite pass picks them up if any get remapped.
        for r in rows:
            for k in (
                "owner_category_name",
                "owner_group_name",
                "owner_user_name",
                "request_ip",
                "request_agent_browser",
                "request_agent_platform",
            ):
                if isinstance(r.get(k), str):
                    r[k] = ""
        if rows:
            self._bump("logs_users", len(rows))
        return rows

    def logs_desktops(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            for k in (
                "owner_category_name",
                "owner_group_name",
                "owner_user_name",
                "desktop_name",
                "deployment_name",
                "request_ip",
                "stopping_ip",
                "request_agent_browser",
                "request_agent_platform",
                "request_agent_version",
                "stopping_agent_browser",
                "stopping_agent_platform",
                "hyp_started",
                "hyp_forced",
            ):
                if isinstance(r.get(k), str):
                    r[k] = ""
            evs = r.get("events")
            if isinstance(evs, list):
                for e in evs:
                    if not isinstance(e, dict):
                        continue
                    for k in (
                        "request_ip",
                        "request_agent_browser",
                        "request_agent_platform",
                        "request_agent_version",
                    ):
                        if isinstance(e.get(k), str):
                            e[k] = ""
        if rows:
            self._bump("logs_desktops", len(rows))
        return rows

    # ---- final cross-table consistency pass ----
    def cross_table_rewrite(self, rows: list[dict]) -> int:
        """Walk one table's rows; replace any string leaf whose value is
        registered in `self.remap` with its mapped value. Returns the
        number of replacements made.
        """
        if not self.remap.maps:
            return 0
        lookup = self.remap.lookup
        replaced = 0

        def walk(o):
            nonlocal replaced
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, str):
                        new = lookup(v)
                        if new is not None and new != v:
                            o[k] = new
                            replaced += 1
                    else:
                        walk(v)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    if isinstance(v, str):
                        new = lookup(v)
                        if new is not None and new != v:
                            o[i] = new
                            replaced += 1
                    else:
                        walk(v)

        for r in rows:
            walk(r)
        return replaced

    def config(self, rows: list[dict]) -> list[dict]:
        anon = lambda: f"anon-{secrets.token_urlsafe(12)}"
        for r in rows:
            auth = r.get("auth") or {}
            ldap = (auth.get("ldap") or {}).get("ldap_config")
            if isinstance(ldap, dict):
                if "bind_dn" in ldap and ldap["bind_dn"]:
                    ldap["bind_dn"] = "cn=anon,dc=example,dc=test"
                if "password" in ldap and ldap["password"]:
                    ldap["password"] = anon()
                if "host" in ldap and ldap["host"]:
                    ldap["host"] = "ldap.example.test"
                if "base_search" in ldap and ldap["base_search"]:
                    ldap["base_search"] = "dc=example,dc=test"
            saml = (auth.get("saml") or {}).get("saml_config")
            if isinstance(saml, dict):
                for k in (
                    "cert",
                    "key",
                    "idp_url",
                    "entity_id",
                    "x509cert",
                    "private_key",
                ):
                    if k in saml and saml[k]:
                        saml[k] = anon()
            google = auth.get("google") or {}
            if isinstance(google, dict):
                for k in ("client_id", "client_secret"):
                    if k in google and google[k]:
                        google[k] = anon()
            # `smtp` block lives at the top of config in IsardVDI
            smtp = r.get("smtp")
            if isinstance(smtp, dict):
                # disable SMTP in dev so mails don't actually fire, but keep
                # plausibly-anonymized values in the secret-bearing fields.
                smtp["enabled"] = False
                smtp["host"] = "smtp.example.test"
                smtp["from"] = "noreply@example.test"
                smtp["username"] = "noreply@example.test"
                smtp["password"] = anon()
            # server-wide WireGuard blocks (keys + Address/endpoint)
            for blob_key in ("vpn_hypers", "vpn_users"):
                self._scrub_wireguard(r.get(blob_key))
            # site-custom strings
            eng = r.get("engine") or {}
            graf = eng.get("grafana") if isinstance(eng, dict) else None
            if isinstance(graf, dict) and isinstance(graf.get("hostname"), str):
                graf["hostname"] = "isard-grafana"
            res = r.get("resources")
            if isinstance(res, dict) and isinstance(res.get("url"), str):
                res["url"] = "https://repository.example.test"
            mt = r.get("maintenance_text")
            if isinstance(mt, dict):
                if isinstance(mt.get("title"), str):
                    mt["title"] = ""
                if isinstance(mt.get("body"), str):
                    mt["body"] = ""
            self._bump("config")
        return rows

    # Catalog / resource tables whose `name`/`description` are admin- or
    # user-authored free text. Verified against the IsardVDI schema: every one
    # of these is referenced elsewhere ONLY by primary-key id (domains store
    # hardware ids, qos_id, etc. — never the catalog name), so the rename needs
    # no cross-table propagation. Blanket-rename name + blank description,
    # matching the interfaces()/media() idiom (built-in default names are
    # public anyway; admin-custom names are the leak). Primary-key `id` is left
    # untouched (e.g. disk_bus ids "virtio"/"sata" are the canonical values).
    _CATALOG_NAME_PREFIX = {
        "user_networks": "usernet",
        "qos_net": "qosnet",
        "qos_disk": "qosdisk",
        "graphics": "graphics",
        "videos": "video",
        "boots": "boot",
        "disk_bus": "diskbus",
        "virt_install": "virtinstall",
        "desktops_priority": "dpriority",
        "bookings_priority": "bpriority",
        "storage_pool": "pool",
        "scheduler_jobs": "job",
        "roles": "role",
        "notification_tmpls": "ntmpl",
    }

    def _scrub_catalog(self, table: str, rows: list[dict]) -> list[dict]:
        prefix = self._CATALOG_NAME_PREFIX[table]
        for r in rows:
            rid = r.get("id", "") or self.faker.pystr(8, 8)
            if isinstance(r.get("name"), str):
                r["name"] = f"{prefix}-{rid[:12]}"
            if isinstance(r.get("description"), str):
                r["description"] = ""
            self._bump(table)
        return rows


# ----- dispatch -----
def get_scrubbers(s: Scrubber) -> dict[str, Callable[[list[dict]], list[dict]]]:
    scrubbers: dict[str, Callable[[list[dict]], list[dict]]] = {
        "users": s.users,
        "domains": s.domains,
        "storage": s.storage,
        "usage_consumption": s.usage_consumption,
        "hypervisors": s.hypervisors,
        "hypervisors_pools": s.hypervisors_pools,
        "targets": s.targets,
        "secrets": s.secrets,
        "remotevpn": s.remotevpn,
        "media": s.media,
        "vouchers": s.vouchers,
        "users_migrations": s.users_migrations,
        "recycle_bin": s.recycle_bin,
        "logs_users": s.logs_users,
        "logs_desktops": s.logs_desktops,
        "config": s.config,
        "categories": s.categories,
        "groups": s.groups,
        "deployments": s.deployments,
        "bookings": s.bookings,
        "interfaces": s.interfaces,
        "notifications_data": s.notifications_data,
        "vgpus": s.vgpus,
        "gpus": s.gpus,
        "engine": s.engine,
    }
    # Generic name/description scrubbers for the id-referenced catalog tables.
    for table in s._CATALOG_NAME_PREFIX:
        scrubbers[table] = partial(s._scrub_catalog, table)
    return scrubbers
