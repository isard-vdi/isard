# SPDX-License-Identifier: AGPL-3.0-or-later

"""Contract test — every apiv4 route declares ``response_model=`` or
``response_class=``.

Pau's audit on #15179 (2026-05-04) flagged 13 endpoints whose decorator
omitted both — the OpenAPI spec then surfaced them with no schema and
the generated clients (Vue 3 ``@hey-api/openapi-ts``, the Python
``isardvdi_apiv4_client``) shipped them as ``Record<string, unknown>``
or ``Any``. Round 4 added the missing declarations route-by-route.

This test pins it: any future ``@router.<verb>(...)`` decorator without
either ``response_model=`` or ``response_class=`` fails CI on the same
push. If a route legitimately can't declare one (e.g. a streaming
download whose body isn't typeable), add it to ``ALLOWLIST`` with a
rationale comment so the next reviewer can challenge it.
"""

import re
from pathlib import Path

# (file, line) tuples of routes whose missing schema is conscious.
# Empty today — keep it that way unless a route truly can't be typed.
ALLOWLIST: set[tuple[str, int]] = set()

_ROUTES_ROOT = Path(__file__).resolve().parent.parent.parent / "routes"

# Captures the start of a route decorator: the ``@<router>.<verb>(``
# token. We then walk forward to the matching close paren so a route
# that spans multiple lines (the common case) is matched as a single
# unit, not chopped up by the regex's backtracking.
_DECORATOR_HEAD = re.compile(r"@(\w+)\.(get|post|put|delete|patch)\(")
# Routers we recognise. Any prefix matching this set is treated as a
# real router; anything else (e.g. a custom decorator) is ignored to
# avoid false positives on test fixtures.
_KNOWN_ROUTER_NAMES = {
    "open_router",
    "token_router",
    "advanced_router",
    "manager_router",
    "admin_router",
    "maintenance_router",
    "register_router",
    "password_reset_router",
    "disclaimer_router",
    "direct_viewer_router",
    "migration_router",
    "external_router",
}


def _python_sources() -> list[Path]:
    out: list[Path] = []
    for path in _ROUTES_ROOT.rglob("*.py"):
        rel = path.relative_to(_ROUTES_ROOT)
        if rel.parts and rel.parts[0] == "tests":
            continue
        if path.name == "__init__.py":
            continue
        out.append(path)
    return sorted(out)


def _iter_decorators(text: str):
    pos = 0
    while True:
        m = _DECORATOR_HEAD.search(text, pos)
        if not m:
            return
        router = m.group(1)
        # Walk to the matching close paren so multi-line decorators
        # (the norm) are captured as a single body.
        depth = 1
        i = m.end()
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = text[m.start() : i]
        line = text[: m.start()].count("\n") + 1
        yield (router, line, body)
        pos = i


def test_every_route_declares_response_model_or_class() -> None:
    """Every routed verb must declare either ``response_model=`` or
    ``response_class=`` on the decorator.

    ``response_model=`` is preferred — it controls both serialisation
    and the OpenAPI schema. ``response_class=`` is the right choice
    for binary / streaming / error-status responses (logo image,
    download CSV, VPN file, 204-only routes). Either is acceptable;
    omitting both means the OpenAPI spec carries no schema for the
    response body and the generated clients can't type it.
    """
    offenders: list[str] = []
    for path in _python_sources():
        rel = str(path.relative_to(_ROUTES_ROOT))
        text = path.read_text(encoding="utf-8")
        for router, line, body in _iter_decorators(text):
            if router not in _KNOWN_ROUTER_NAMES:
                continue
            if "response_model=" in body or "response_class=" in body:
                continue
            if (rel, line) in ALLOWLIST:
                continue
            # Trim the body for the offender message — the full multi-
            # line decorator is too noisy.
            head = body.split("\n", 1)[0]
            offenders.append(f"  {rel}:{line}: {head}")

    assert not offenders, (
        "OpenAPI contract: every route must declare ``response_model=`` "
        "or ``response_class=`` on its decorator. The following routes "
        "ship without either, so the generated client can't type their "
        "response body:\n" + "\n".join(offenders)
    )


def test_routes_root_is_present() -> None:
    assert _ROUTES_ROOT.is_dir(), _ROUTES_ROOT
    assert _ROUTES_ROOT.name == "routes"


def test_python_sources_finds_real_files() -> None:
    rels = {str(p.relative_to(_ROUTES_ROOT)) for p in _python_sources()}
    # At least one well-known route file must be discovered.
    assert any(r.endswith("deployments.py") for r in rels), sorted(rels)[:5]
