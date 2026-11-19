# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route matching contexts are built at boot, not on the first request."""

import asyncio

import fastapi.routing as fastapi_routing
import pytest
from api import _warm_route_matching
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


def _app():
    application = FastAPI()
    for prefix in ("/a", "/b", "/c"):
        router = APIRouter()
        for name in ("x", "y", "z"):

            @router.get(f"/{name}")
            async def endpoint():
                return {}

        application.include_router(router, prefix=prefix)
    return application


@pytest.fixture
def builds(monkeypatch):
    """Count the per-route matching contexts FastAPI builds."""
    counter = {"n": 0}
    original = fastapi_routing._EffectiveRouteContext.from_api_route

    def counting(*args, **kwargs):
        counter["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        fastapi_routing._EffectiveRouteContext,
        "from_api_route",
        staticmethod(counting),
    )
    return counter


def test_first_request_builds_the_contexts_without_warmup(builds):
    # Control: this is the cost the warm-up moves to boot.
    client = TestClient(_app())
    assert client.get("/c/z").status_code == 200
    assert builds["n"] > 0


def test_after_warmup_the_first_request_builds_nothing(builds):
    application = _app()
    asyncio.run(_warm_route_matching(application))
    warmed = builds["n"]
    assert warmed > 0
    client = TestClient(application)
    assert client.get("/c/z").status_code == 200
    assert client.get("/a/x").status_code == 200
    assert builds["n"] == warmed


def test_warmup_never_raises(monkeypatch):
    application = _app()

    async def broken(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(application, "router", broken)
    asyncio.run(_warm_route_matching(application))  # logged, not raised
