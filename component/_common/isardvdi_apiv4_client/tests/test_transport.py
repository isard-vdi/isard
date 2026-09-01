"""Contract tests for the process-wide shared httpx transport."""

import httpx
import pytest
from isardvdi_apiv4_client_auth import _transport
from isardvdi_apiv4_client_auth._transport import (
    POOL_TIMEOUT,
    SharedTransport,
    _clear_transports_for_tests,
    shared_transport,
)


@pytest.fixture(autouse=True)
def clean_transports():
    _clear_transports_for_tests()
    yield
    _clear_transports_for_tests()


class RecordingTransport(httpx.BaseTransport):
    """Stand-in for httpx.HTTPTransport that records what happens to it."""

    def __init__(self):
        self.closed = 0
        self.requests = 0

    def handle_request(self, request):
        self.requests += 1
        return httpx.Response(204, request=request)

    def close(self):
        self.closed += 1


def test_same_verify_returns_the_same_transport():
    assert shared_transport(verify=False) is shared_transport(verify=False)


def test_verify_variants_do_not_share_a_pool():
    assert shared_transport(verify=True) is not shared_transport(verify=False)


def test_wraps_an_httpx_transport():
    assert isinstance(shared_transport(verify=False).inner, httpx.HTTPTransport)


def test_close_does_not_close_the_pool():
    recorded = RecordingTransport()
    wrapped = SharedTransport(recorded)

    wrapped.close()

    assert recorded.closed == 0


def test_leaving_an_httpx_context_does_not_close_the_pool():
    """httpx exits through __exit__, which SharedTransport only inherits."""
    recorded = RecordingTransport()
    wrapped = SharedTransport(recorded)

    with httpx.Client(transport=wrapped):
        pass

    assert recorded.closed == 0


def test_requests_are_delegated_to_the_pool():
    recorded = RecordingTransport()
    wrapped = SharedTransport(recorded)

    with httpx.Client(transport=wrapped) as client:
        response = client.get("http://isard-apiv4:5000/api/v4/health")

    assert response.status_code == 204
    assert recorded.requests == 1


def test_the_cache_is_keyed_by_pid(monkeypatch):
    """So that a process forked after a request builds its own pool
    instead of writing to sockets its parent still owns."""
    parent = shared_transport(verify=False)

    monkeypatch.setattr(_transport, "getpid", lambda: -1)

    assert shared_transport(verify=False) is not parent


def test_the_pool_wait_is_bounded():
    """Sharing introduced a queue; hanging on it forever is not an option."""
    assert POOL_TIMEOUT.pool is not None


def test_idle_connections_outlive_a_polling_loop_but_not_the_api():
    """httpx expires an idle connection after 5s, shorter than any of the
    loops that call the API, so sharing the pool would still buy nothing.
    It has to expire before apiv4's own --timeout-keep-alive (120s, in
    component/apiv4/docker/Dockerfile): whoever holds on longer ends up
    racing the other's close."""
    expiry = shared_transport(verify=False).inner._pool._keepalive_expiry

    assert httpx.Limits().keepalive_expiry < expiry < 120
