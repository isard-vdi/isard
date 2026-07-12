#!/usr/bin/env python3
"""isard-config — read/write IsardVDI admin runtime settings over the public API.

Standalone ops tool (Python 3 stdlib only). Point it at any IsardVDI install by
base URL, log in as an admin (prompted, never on argv), then GET (dump) or SET
the runtime-configurable "neteja/retenció" admin settings that live in the
RethinkDB ``config``/``scheduler`` tables and are exposed through apiv4 admin
REST routes.

Usage:
    isard_config.py --url https://<domain> [--category default] [--insecure]
        (default GET: dump every supported setting, grouped + human readable)
    isard_config.py --url ... --json
    isard_config.py --url ... --set recycle_bin_cutoff=720
    isard_config.py --url ... --set logs_desktops.max_time=365 --set logs_desktops.action=delete
    isard_config.py --url ... --set old_tasks.older_than=604800 --set old_tasks.enabled=true
    isard_config.py --url ... --list-schedulers

Username is prompted (or --user); password is always prompted via getpass.
Endpoints/payloads were discovered from apiv4 source and verified live against a
running stack.
"""

import argparse
import base64
import getpass
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Setting registry (pure data)
# ---------------------------------------------------------------------------


class Setting:
    """One SET-able configuration key.

    set_kind:
      - "path"         : value goes in the URL path (no body)
      - "body_field"   : PUT a JSON body {set_body_field: value}
      - "whole_object" : PUT the whole group object, merging the changed field
                         onto the current values (requires a fresh GET first)
    """

    def __init__(
        self,
        key,
        group,
        label,
        vtype,
        set_kind,
        set_endpoint,
        set_body_field=None,
        choices=None,
        minimum=None,
        maximum=None,
        unit=None,
        allow_none=False,
    ):
        self.key = key
        self.group = group  # which GROUP its current value is read from
        self.label = label
        self.vtype = vtype  # "int" | "bool" | "str"
        self.set_kind = set_kind
        self.set_endpoint = set_endpoint  # str, may contain "{value}"
        self.set_body_field = set_body_field
        self.choices = choices
        self.minimum = minimum
        self.maximum = maximum
        self.unit = unit
        self.allow_none = allow_none


class Group:
    """A GET-able group of settings read from a single endpoint."""

    def __init__(self, name, title, endpoint, fields):
        self.name = name
        self.title = title
        self.endpoint = endpoint
        # ordered mapping: response_field -> human label
        self.fields = fields


# GET groups — one HTTP GET per group, all verified live.
GROUPS = [
    Group(
        "recycle_bin",
        "Recycle bin — system cutoff",
        "/api/v4/item/recycle-bin/system/cutoff-time",
        {"recycle_bin_cuttoff_time": "cutoff (hours)"},
    ),
    Group(
        "recycle_bin_old_entries",
        "Recycle bin — old-entries retention",
        "/api/v4/item/recycle-bin/old-entries/config",
        {"max_time": "max_time", "action": "action (delete/keep)"},
    ),
    Group(
        "logs_desktops",
        "Logs desktops — retention",
        "/api/v4/admin/item/logs_desktops/config/old_entries",
        {"max_time": "max_time (hours)", "action": "action"},
    ),
    Group(
        "logs_users",
        "Logs users — retention",
        "/api/v4/admin/item/logs_users/config/old_entries",
        {"max_time": "max_time (hours)", "action": "action"},
    ),
    Group(
        "old_tasks",
        "Redis tasks — auto delete",
        "/api/v4/admin/item/queues/old_tasks/config",
        {
            "older_than": "older_than (seconds)",
            "enabled": "enabled",
            "queue_registries": "queue_registries",
        },
    ),
    Group(
        "usage",
        "Usage/consumption — retention (months)",
        "/api/v4/admin/item/usage/retention",
        {
            "daily_months": "daily_months",
            "weekly_months": "weekly_months",
            "total_months": "total_months",
        },
    ),
]

GROUPS_BY_NAME = {g.name: g for g in GROUPS}

SCHEDULER_ENDPOINTS = [
    ("system", "/api/v4/admin/items/scheduler/jobs/system"),
    ("bookings", "/api/v4/admin/items/scheduler/jobs/bookings"),
]

# SET keys.
_SETTINGS_LIST = [
    Setting(
        "recycle_bin_cutoff",
        "recycle_bin",
        "Recycle bin system cutoff",
        "int",
        "body_field",
        "/api/v4/item/recycle-bin/system/cutoff-time",
        set_body_field="recycle_bin_cuttoff_time",
        minimum=1,
        unit="hours",
    ),
    Setting(
        "logs_desktops.max_time",
        "logs_desktops",
        "Desktop logs retention age",
        "int",
        "path",
        "/api/v4/admin/item/logs_desktops/config/old_entries/max_time/{value}",
        minimum=24,
        unit="hours",
    ),
    Setting(
        "logs_desktops.action",
        "logs_desktops",
        "Desktop logs old-entries action",
        "str",
        "path",
        "/api/v4/admin/item/logs_desktops/config/old_entries/action/{value}",
        choices=["delete", "none"],
    ),
    Setting(
        "logs_users.max_time",
        "logs_users",
        "User logs retention age",
        "int",
        "path",
        "/api/v4/admin/item/logs_users/config/old_entries/max_time/{value}",
        minimum=24,
        unit="hours",
    ),
    Setting(
        "logs_users.action",
        "logs_users",
        "User logs old-entries action",
        "str",
        "path",
        "/api/v4/admin/item/logs_users/config/old_entries/action/{value}",
        choices=["delete", "none"],
    ),
    Setting(
        "old_tasks.older_than",
        "old_tasks",
        "Redis old-tasks age",
        "int",
        "path",
        "/api/v4/admin/item/queues/old_tasks/config/max_time/{value}",
        minimum=86400,
        unit="seconds",
    ),
    Setting(
        "old_tasks.enabled",
        "old_tasks",
        "Redis old-tasks auto-delete enabled",
        "bool",
        "body_field",
        "/api/v4/admin/item/queues/old_tasks/config/enabled",
        set_body_field="enabled",
    ),
    # Bounds below come from the authoritative OpenAPI spec
    # (components.schemas.UsageRetentionConfig): daily min1/max120,
    # weekly min2/max120, total min1/max240 (nullable).
    Setting(
        "usage.daily_months",
        "usage",
        "Usage daily granularity",
        "int",
        "whole_object",
        "/api/v4/admin/item/usage/retention",
        set_body_field="daily_months",
        minimum=1,
        maximum=120,
        unit="months",
    ),
    Setting(
        "usage.weekly_months",
        "usage",
        "Usage weekly granularity",
        "int",
        "whole_object",
        "/api/v4/admin/item/usage/retention",
        set_body_field="weekly_months",
        minimum=2,
        maximum=120,
        unit="months",
    ),
    Setting(
        "usage.total_months",
        "usage",
        "Usage hard-delete horizon (optional)",
        "int",
        "whole_object",
        "/api/v4/admin/item/usage/retention",
        set_body_field="total_months",
        minimum=1,
        maximum=240,
        unit="months",
        allow_none=True,
    ),
]

SETTINGS = {s.key: s for s in _SETTINGS_LIST}


def get_setting(key):
    """Look up a Setting by key. Raises KeyError with a helpful message."""
    try:
        return SETTINGS[key]
    except KeyError:
        raise KeyError(
            f"unknown key {key!r}. Valid keys: {', '.join(sorted(SETTINGS))}"
        )


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def normalize_base_url(url):
    """Return a bare scheme://host[:port] with no trailing slash or path."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme or "https"
    return f"{scheme}://{parts.netloc}"


def build_login_url(base_url, category_id, provider="form"):
    q = urllib.parse.urlencode({"provider": provider, "category_id": category_id})
    return f"{base_url}/authentication/login?{q}"


def parse_set_arg(s):
    """Split 'key=value' into (key, value). Value may itself contain '='."""
    if "=" not in s:
        raise ValueError(f"--set expects KEY=VALUE, got {s!r}")
    key, value = s.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"--set has an empty key: {s!r}")
    return key, value


_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}
_NULLISH = {"", "null", "none"}


def coerce_value(setting, raw):
    """Type-coerce + validate a raw string for a Setting. Raises ValueError."""
    if setting.allow_none and raw.strip().lower() in _NULLISH:
        return None

    if setting.vtype == "int":
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{setting.key}: expected an integer, got {raw!r}")
        unit = (" " + setting.unit) if setting.unit else ""
        if setting.minimum is not None and val < setting.minimum:
            raise ValueError(
                f"{setting.key}: minimum is {setting.minimum}{unit}, got {val}"
            )
        if setting.maximum is not None and val > setting.maximum:
            raise ValueError(
                f"{setting.key}: maximum is {setting.maximum}{unit}, got {val}"
            )
        return val

    if setting.vtype == "bool":
        low = raw.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise ValueError(f"{setting.key}: expected a boolean (true/false), got {raw!r}")

    if setting.vtype == "str":
        val = raw.strip()
        if setting.choices is not None and val not in setting.choices:
            raise ValueError(
                f"{setting.key}: must be one of {setting.choices}, got {val!r}"
            )
        return val

    raise ValueError(f"{setting.key}: unsupported type {setting.vtype!r}")


def build_set_request(setting, value, current=None):
    """Return (method, path, body) for applying `value` to `setting`.

    body is None for path-kind sets, else a dict to be JSON-encoded.
    `current` (the group's current GET dict) is required for whole_object sets.
    """
    if setting.set_kind == "path":
        path = setting.set_endpoint.format(value=_path_value(value))
        return "PUT", path, None

    if setting.set_kind == "body_field":
        return "PUT", setting.set_endpoint, {setting.set_body_field: value}

    if setting.set_kind == "whole_object":
        if current is None:
            raise ValueError(f"{setting.key}: whole_object set requires current values")
        body = dict(current)
        body[setting.set_body_field] = value
        # Keep only the fields the endpoint expects for this group.
        allowed = set(GROUPS_BY_NAME[setting.group].fields)
        body = {k: v for k, v in body.items() if k in allowed}
        return "PUT", setting.set_endpoint, body

    raise ValueError(f"{setting.key}: unsupported set_kind {setting.set_kind!r}")


def _path_value(value):
    if isinstance(value, bool):  # guard: bool is a subclass of int
        return "true" if value else "false"
    return str(value)


def _b64url_decode(seg):
    seg += "=" * (-len(seg) % 4)  # restore stripped padding
    return base64.urlsafe_b64decode(seg.encode())


def decode_jwt_payload(token):
    """Decode a JWT's payload (middle segment) into a dict. No signature check.

    We only read our own freshly-issued token to gate on role locally; the API
    is still the real authority (it enforces the admin gate server-side).
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT (expected 3 dot-separated segments)")
    try:
        return json.loads(_b64url_decode(parts[1]))
    except Exception as e:
        raise ValueError(f"could not decode JWT payload: {e}")


def token_role(payload):
    """Extract role_id from a decoded IsardVDI JWT payload."""
    data = payload.get("data") or {}
    return data.get("role_id")


def is_admin_payload(payload):
    return token_role(payload) == "admin"


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, status, body, url):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} for {url}: {body}")


class Client:
    def __init__(self, base_url, insecure=False, timeout=30):
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        self.token = None
        if insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._ctx = ctx
        else:
            self._ctx = ssl.create_default_context()

    # -- low level -----------------------------------------------------------
    def _open(self, req):
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ctx
            ) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _auth_headers(self):
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get_json(self, path):
        url = self.base_url + path
        req = urllib.request.Request(url, headers=self._auth_headers(), method="GET")
        status, _, body = self._open(req)
        text = body.decode("utf-8", "replace")
        if status != 200:
            raise ApiError(status, text, url)
        return json.loads(text) if text else None

    def put_json(self, path, body):
        url = self.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        headers = self._auth_headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        status, _, raw = self._open(req)
        text = raw.decode("utf-8", "replace")
        if status not in (200, 201, 204):
            raise ApiError(status, text, url)
        return json.loads(text) if text else None

    # -- auth ----------------------------------------------------------------
    def login(self, category_id, username, password, provider="form"):
        """Log in via the form provider (multipart body) and store the JWT."""
        url = build_login_url(self.base_url, category_id, provider)
        body, content_type = _multipart({"username": username, "password": password})
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": content_type}, method="POST"
        )
        status, headers, raw = self._open(req)
        text = raw.decode("utf-8", "replace")
        if status != 200:
            raise ApiError(status, text, url)
        auth = headers.get("Authorization") or headers.get("authorization")
        token = None
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        elif text:
            # some deployments return the token in the JSON body
            try:
                j = json.loads(text)
                token = j.get("token") or j.get("jwt")
            except Exception:
                token = None
        if not token:
            raise ApiError(status, f"login ok but no token found (body={text!r})", url)
        self.token = token
        return token

    def list_categories(self):
        return self.get_json("/api/v4/items/categories").get("categories", [])


def _multipart(fields):
    """Build a minimal multipart/form-data body from a dict of str fields."""
    boundary = "----isardconfig7c2b1f9e0d4a"
    lines = []
    for name, value in fields.items():
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{name}"')
        lines.append("")
        lines.append(str(value))
    lines.append(f"--{boundary}--")
    lines.append("")
    body = "\r\n".join(lines).encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def fetch_all(client):
    """GET every group; return {group_name: dict_or_error_marker}."""
    out = {}
    for g in GROUPS:
        try:
            out[g.name] = client.get_json(g.endpoint)
        except ApiError as e:
            out[g.name] = {"__error__": f"HTTP {e.status}: {e.body[:200]}"}
    return out


def fetch_schedulers(client):
    out = {}
    for name, path in SCHEDULER_ENDPOINTS:
        try:
            out[name] = client.get_json(path)
        except ApiError as e:
            out[name] = {"__error__": f"HTTP {e.status}: {e.body[:200]}"}
    return out


def _fmt(value):
    if value is None:
        return "(not set)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_get(data, use_json=False):
    if use_json:
        return json.dumps(data, indent=2, sort_keys=True)
    lines = []
    for g in GROUPS:
        lines.append(f"== {g.title} ==")
        gd = data.get(g.name) or {}
        if isinstance(gd, dict) and "__error__" in gd:
            lines.append(f"  ! {gd['__error__']}")
            lines.append("")
            continue
        for field, label in g.fields.items():
            val = gd.get(field) if isinstance(gd, dict) else None
            lines.append(f"  {label:<26} : {_fmt(val)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_schedulers(sched, use_json=False):
    if use_json:
        return json.dumps(sched, indent=2, sort_keys=True)
    lines = []
    for name, _ in SCHEDULER_ENDPOINTS:
        jobs = sched.get(name)
        lines.append(f"== Scheduler jobs: {name} ==")
        if isinstance(jobs, dict) and "__error__" in jobs:
            lines.append(f"  ! {jobs['__error__']}")
        elif not jobs:
            lines.append("  (none)")
        else:
            for job in jobs:
                jid = job.get("id", "?")
                kind = job.get("kind", "?")
                nxt = job.get("next_run_time")
                lines.append(f"  {jid:<52} [{kind}] next={nxt}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def current_value_for(setting, data):
    """Pull the current stored value of a setting out of a fetch_all() dict."""
    gd = data.get(setting.group) or {}
    if not isinstance(gd, dict):
        return None
    field = setting.set_body_field
    if setting.set_kind == "body_field" and setting.group == "recycle_bin":
        field = "recycle_bin_cuttoff_time"
    if field and field in gd:
        return gd.get(field)
    # path-kind settings map onto the group's GET field of the same tail name
    tail = setting.key.split(".")[-1]
    return gd.get(tail)


def do_set(
    client,
    set_args,
    assume_yes=False,
    verify_timeout=20.0,
    sleeper=time.sleep,
    clock=time.monotonic,
    out=sys.stdout,
):
    """Apply one or more KEY=VALUE sets with old->new confirmation + re-read.

    The write PUT returning 2xx is the authoritative "applied" signal. The
    re-read is a best-effort confirmation that must tolerate apiv4's server-side
    read caches (the config getters are @cached with TTLs of 5-60s and the
    setters do NOT invalidate them). So we poll the re-read up
    to `verify_timeout` seconds until it reflects the new value.
    """
    # Parse + validate everything first (fail fast, before any mutation).
    planned = []
    for raw in set_args:
        try:
            key, rawval = parse_set_arg(raw)
            setting = get_setting(key)
            value = coerce_value(setting, rawval)
        except KeyError as e:
            # unknown key — message already lists the valid keys
            print(f"Error: {e.args[0] if e.args else e}", file=sys.stderr)
            return 1
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        planned.append((setting, value))

    before = fetch_all(client)

    print("Planned changes:", file=out)
    for setting, value in planned:
        old = current_value_for(setting, before)
        print(f"  {setting.key}: {_fmt(old)} -> {_fmt(value)}", file=out)

    if not assume_yes:
        try:
            ans = input("Apply these changes? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            print("Aborted; nothing changed.", file=out)
            return 1

    for setting, value in planned:
        if setting.set_kind == "whole_object":
            current = before.get(setting.group) or {}
            method, path, body = build_set_request(setting, value, current=current)
        else:
            method, path, body = build_set_request(setting, value)
        client.put_json(path, body)  # 2xx-or-raise => authoritative "applied"
        print(f"  applied {setting.key} (PUT accepted)", file=out)

    print("\nVerification (re-read, polling past server cache TTL):", file=out)
    pending = {s.key: (s, v) for s, v in planned}
    confirmed = {}
    deadline = clock() + verify_timeout
    while pending:
        after = fetch_all(client)
        for key in list(pending):
            setting, value = pending[key]
            if current_value_for(setting, after) == value:
                confirmed[key] = clock()
                del pending[key]
        if not pending or clock() >= deadline:
            break
        sleeper(2)

    ok = not pending
    for setting, value in planned:
        if setting.key not in pending:
            print(f"  {setting.key}: now {_fmt(value)} [CONFIRMED]", file=out)
        else:
            newval = current_value_for(setting, fetch_all(client))
            print(
                f"  {setting.key}: PUT accepted (written) but re-read still shows "
                f"{_fmt(newval)} after {verify_timeout:g}s — apiv4 read cache "
                f"still warm (not a write failure) [UNCONFIRMED]",
                file=out,
            )
    return 0 if ok else 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="isard-config",
        description="Read/write IsardVDI admin runtime settings over the public API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--url", required=True, help="Base URL/domain of the install")
    p.add_argument(
        "--category", default="default", help="Category name/id (default: default)"
    )
    p.add_argument("--user", help="Admin username (prompted if omitted)")
    p.add_argument(
        "--insecure", "-k", action="store_true", help="Skip TLS verification"
    )
    p.add_argument(
        "--json", action="store_true", help="Emit JSON instead of pretty text"
    )
    p.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set a setting (repeatable). See --list-keys.",
    )
    p.add_argument(
        "--yes", "-y", action="store_true", help="Do not ask for confirmation on --set"
    )
    p.add_argument(
        "--verify-timeout",
        type=float,
        default=20.0,
        help="Seconds to poll the re-read after a SET, to outlast apiv4 read caches (default 20)",
    )
    p.add_argument(
        "--list-schedulers", action="store_true", help="List scheduler jobs (read-only)"
    )
    p.add_argument(
        "--list-keys", action="store_true", help="List valid --set keys and exit"
    )
    return p


def print_keys(out=sys.stdout):
    print("Valid --set keys:", file=out)
    for key in sorted(SETTINGS):
        s = SETTINGS[key]
        extra = []
        if s.choices:
            extra.append("choices=" + "|".join(s.choices))
        if s.minimum is not None:
            extra.append(f"min={s.minimum}")
        if s.unit:
            extra.append(s.unit)
        if s.allow_none:
            extra.append("nullable")
        suffix = ("  (" + ", ".join(extra) + ")") if extra else ""
        print(f"  {key:<24} {s.vtype}{suffix}", file=out)


def resolve_category(client, wanted):
    """Match --category against id or name; return the category id."""
    cats = client.list_categories()
    for c in cats:
        if wanted in (c.get("id"), c.get("name"), c.get("custom_url_name")):
            return c.get("id")
    names = ", ".join(f"{c.get('name')}({c.get('id')})" for c in cats)
    raise SystemExit(f"Category {wanted!r} not found. Available: {names}")


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.list_keys:
        print_keys()
        return 0

    client = Client(args.url, insecure=args.insecure)

    # Resolve category (also confirms API reachability).
    try:
        category_id = resolve_category(client, args.category)
    except ApiError as e:
        print(f"Could not reach the API: {e}", file=sys.stderr)
        return 1

    username = args.user or input("Username: ").strip()
    password = getpass.getpass("Password: ")

    # Login.
    try:
        token = client.login(category_id, username, password)
    except ApiError as e:
        if e.status in (401, 403):
            print(
                "Login failed: bad username/password or user not allowed.",
                file=sys.stderr,
            )
        else:
            print(f"Login failed: {e}", file=sys.stderr)
        return 1

    # Admin gate (local decode + the API enforces it too).
    try:
        payload = decode_jwt_payload(token)
    except ValueError as e:
        print(f"Could not verify token role: {e}", file=sys.stderr)
        return 1
    if not is_admin_payload(payload):
        print(
            f"Refusing to continue: logged-in user role is "
            f"{token_role(payload)!r}, admin is required.",
            file=sys.stderr,
        )
        return 3

    # Actions.
    if args.sets:
        return do_set(
            client, args.sets, assume_yes=args.yes, verify_timeout=args.verify_timeout
        )

    if args.list_schedulers:
        sched = fetch_schedulers(client)
        sys.stdout.write(render_schedulers(sched, use_json=args.json))
        return 0

    # Default: GET dump.
    data = fetch_all(client)
    sys.stdout.write(render_get(data, use_json=args.json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
