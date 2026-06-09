#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""B3 contract — every FastAPI endpoint MUST declare ``response_model=``
unless its handler legitimately returns a raw
``Response``/``StreamingResponse``/``PlainTextResponse``/``FileResponse``
(Bucket B). Bucket B is allowlisted explicitly so a new endpoint
without ``response_model=`` fails CI rather than silently
re-introducing 500-on-datetime serialisation regressions.

Adding an entry to ``BUCKET_B_ALLOWLIST`` implies the route's handler
returns a non-JSON body (binary, plain text, CSV, 204). Removing
``response_model=`` from a handler that returns dict/list is not
acceptable — it must round-trip through FastAPI's ``jsonable_encoder``.
The allowlist must shrink, never grow.
"""

from fastapi.routing import APIRoute

# (method, path) pairs whose handlers return a raw
# Response / StreamingResponse / PlainTextResponse / FileResponse
# or a 204 No Content. Verified against handler bodies on 2026-04-30.
BUCKET_B_ALLOWLIST: set[tuple[str, str]] = {
    # PlainTextResponse / raw image bytes
    ("GET", "/api/v4/item/category/{category_id}/custom_url"),
    ("GET", "/api/v4/logo"),
    ("GET", "/api/v4/logo/category/{category_id}"),
    # 204 No Content
    ("PUT", "/api/v4/item/deployment/{deployment_id}/stop"),
    ("PUT", "/api/v4/item/deployment/{deployment_id}/user/{user_id}/stop"),
    ("PUT", "/api/v4/item/deployment/{deployment_id}/start"),
    ("GET", "/api/v4/storage-pools/check-create-availability"),
    ("GET", "/api/v4/quota/media/new"),
    ("GET", "/api/v4/quota/desktop/new"),
    ("GET", "/api/v4/quota/template/new"),
    ("GET", "/api/v4/quota/deployment/new"),
    ("PUT", "/api/v4/item/user/reset-vpn"),
    # CSV / file download
    ("GET", "/api/v4/item/deployment/{deployment_id}/download-csv"),
    # StreamingResponse — VPN config bytes
    ("GET", "/api/v4/item/user/get-vpn"),
}


def _routes_without_response_model() -> list[tuple[str, str, str]]:
    from api import app

    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.response_model is not None:
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            if (method, route.path) in BUCKET_B_ALLOWLIST:
                continue
            offenders.append((method, route.path, route.endpoint.__name__))
    return sorted(offenders)


def test_every_route_declares_response_model():
    """B3 invariant: an endpoint lacking ``response_model=`` must either be
    decorated or added to ``BUCKET_B_ALLOWLIST`` in this file."""
    offenders = _routes_without_response_model()
    if offenders:
        listing = "\n  ".join(f"{m} {p} -> {n}" for m, p, n in offenders)
        raise AssertionError(
            "Endpoints without response_model= and not in "
            "BUCKET_B_ALLOWLIST. Either add response_model= to the "
            "route decorator, or — if the handler legitimately returns "
            "Response / StreamingResponse / PlainTextResponse / "
            "FileResponse — append the (method, path) tuple to "
            "BUCKET_B_ALLOWLIST in this test file.\n\n"
            f"Offenders:\n  {listing}"
        )


def test_bucket_b_allowlist_has_no_stale_entries():
    """Allowlist must shrink, never grow. A stale entry means a route was
    renamed or removed without the allowlist being updated."""
    from api import app

    real_routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "HEAD"
    }
    stale = BUCKET_B_ALLOWLIST - real_routes
    assert not stale, (
        "BUCKET_B_ALLOWLIST has stale entries (route renamed or "
        f"removed): {sorted(stale)}"
    )
