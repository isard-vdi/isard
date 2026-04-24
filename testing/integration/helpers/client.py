# SPDX-License-Identifier: AGPL-3.0-or-later

"""Thin REST client for the integration suite.

Runs against a full IsardVDI stack reachable on the docker-compose
network — `http://isard-authentication:1313`, `http://isard-apiv4:5000`,
`http://isard-socketio:5000`. The DinD CI job brings up the stack and
runs pytest inside a sidecar container on the same network; locally the
developer does the same via `docker compose run --rm integration-test`.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests


class IsardClient:
    """Authenticated HTTP client for apiv4 and the authentication service."""

    def __init__(
        self,
        apiv4_url: Optional[str] = None,
        auth_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.apiv4_url = (
            apiv4_url or os.environ.get("APIV4_URL") or "http://isard-apiv4:5000"
        ).rstrip("/")
        self.auth_url = (
            auth_url or os.environ.get("AUTH_URL") or "http://isard-authentication:1313"
        ).rstrip("/")
        self.timeout = timeout
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self._session = requests.Session()
        self._login_args: Optional[tuple] = None

    def login(
        self,
        username: str,
        password: str,
        category_id: str = "default",
        provider: str = "form",
    ) -> str:
        # Remember the credentials so we can transparently refresh the
        # token if it expires mid-test. Long-running suites
        # (download_url + qcow2 create + start/stop cycles) routinely
        # outlive the JWT TTL.
        self._login_args = (username, password, category_id, provider)
        resp = self._session.post(
            f"{self.auth_url}/authentication/login",
            params={"provider": provider, "category_id": category_id},
            files={
                "username": (None, username),
                "password": (None, password),
            },
            headers={"X-Forwarded-For": "127.0.0.1"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"login failed for {username}: HTTP {resp.status_code} {resp.text}"
            )
        self.token = resp.text.strip()
        details = self.get("/api/v4/item/user/get-details")
        self.user_id = details["id"]
        return self.token

    def _relogin(self) -> None:
        """Refresh the JWT in place. No-op if no prior login() was made."""
        if not self._login_args:
            return
        username, password, category_id, provider = self._login_args
        resp = self._session.post(
            f"{self.auth_url}/authentication/login",
            params={"provider": provider, "category_id": category_id},
            files={
                "username": (None, username),
                "password": (None, password),
            },
            headers={"X-Forwarded-For": "127.0.0.1"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            self.token = resp.text.strip()

    # --- REST primitives -------------------------------------------------

    def _headers(self) -> dict:
        if not self.token:
            raise RuntimeError("call login() before issuing requests")
        return {"Authorization": f"Bearer {self.token}"}

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.apiv4_url}{path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Any] = None,
        params: Optional[dict] = None,
        expected: Optional[tuple] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        def _send():
            return self._session.request(
                method,
                self._url(path),
                json=json_body,
                params=params,
                headers=self._headers(),
                timeout=timeout or self.timeout,
            )

        resp = _send()
        # Long-running tests routinely outlive the JWT TTL. Retry once
        # after refreshing the token before reporting an assertion error
        # — without this the suite is full of false positives the moment
        # the worker hits a multi-minute download/create.
        if resp.status_code in (401, 403) and self._login_args:
            try:
                self._relogin()
            except Exception:
                pass
            else:
                resp = _send()
        if expected is not None and resp.status_code not in expected:
            raise AssertionError(
                f"{method} {path} -> HTTP {resp.status_code}; expected {expected}; body={resp.text[:500]}"
            )
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def get(self, path: str, **kw) -> Any:
        return self.request("GET", path, expected=kw.pop("expected", (200,)), **kw)

    def post(self, path: str, json_body=None, **kw) -> Any:
        return self.request(
            "POST",
            path,
            json_body=json_body,
            expected=kw.pop("expected", (200, 201)),
            **kw,
        )

    def put(self, path: str, json_body=None, **kw) -> Any:
        return self.request(
            "PUT",
            path,
            json_body=json_body,
            expected=kw.pop("expected", (200, 204)),
            **kw,
        )

    def delete(self, path: str, json_body=None, **kw) -> Any:
        return self.request(
            "DELETE",
            path,
            json_body=json_body,
            expected=kw.pop("expected", (200, 204)),
            **kw,
        )

    # --- raw request (no expectation) — used by cleanup/polling ---------

    def raw(self, method: str, path: str, **kw) -> requests.Response:
        timeout = kw.pop("timeout", self.timeout)

        def _send():
            return self._session.request(
                method,
                self._url(path),
                headers=self._headers(),
                timeout=timeout,
                **kw,
            )

        resp = _send()
        if resp.status_code in (401, 403) and self._login_args:
            try:
                self._relogin()
            except Exception:
                pass
            else:
                resp = _send()
        return resp

    # --- domain-status polling ------------------------------------------

    def poll_desktop_status(
        self,
        desktop_id: str,
        want: set,
        max_wait: float = 90.0,
        interval: float = 2.0,
    ) -> str:
        return self._poll_status(
            f"/api/v4/item/desktop/{desktop_id}",
            want,
            max_wait,
            interval,
        )

    def wait_for_template_created(
        self,
        source_desktop_id: str,
        template_id: str,
        max_wait: float = 180.0,
        interval: float = 2.0,
    ) -> None:
        """Wait until the template-creation task chain finishes.

        apiv4 has no GET that exposes a template's ``status`` field
        (``/items/templates`` and ``/admin/domains?kind=template`` both
        pluck it out). Instead, observe the source desktop: apiv4
        inserts the template row immediately (status ``CreatingTemplate``)
        and flips the desktop to the same status, then fires the
        isard-storage move/create chain. The chain's final
        ``storage_update`` promotes both rows back to ``Stopped``. We
        poll both:
        (1) the source desktop back to Stopped, AND
        (2) the template id visible in ``/items/templates``.
        """
        deadline = time.monotonic() + max_wait
        desktop_back_to_stopped = False
        template_in_list = False
        last_desktop_status: Optional[str] = None
        while time.monotonic() < deadline:
            if not desktop_back_to_stopped:
                resp = self.raw("GET", f"/api/v4/item/desktop/{source_desktop_id}")
                if resp.status_code == 200:
                    last_desktop_status = (resp.json() or {}).get("status")
                    if last_desktop_status == "Stopped":
                        desktop_back_to_stopped = True
            if not template_in_list:
                resp = self.raw("GET", "/api/v4/items/templates")
                if resp.status_code == 200:
                    ids = {
                        t.get("id") for t in (resp.json() or {}).get("templates", [])
                    }
                    template_in_list = template_id in ids
            if desktop_back_to_stopped and template_in_list:
                return
            time.sleep(interval)
        raise TimeoutError(
            "template {} not created within {}s (desktop last status={!r}, "
            "template in list={})".format(
                template_id,
                max_wait,
                last_desktop_status,
                template_in_list,
            )
        )

    MEDIA_TERMINAL_FAILURE = frozenset(
        {"DownloadFailed", "DownloadFailedInvalidFormat"}
    )

    def poll_media_status(
        self,
        media_id: str,
        want: set,
        max_wait: float = 300.0,
        interval: float = 2.0,
    ) -> str:
        """Like ``_poll_status`` but fails fast on terminal failure states.

        If the media status reaches ``DownloadFailed`` /
        ``DownloadFailedInvalidFormat`` (archive.org hiccup, malformed
        file) the poll raises a ``RuntimeError`` immediately instead of
        waiting for the timeout — that lets the test decide whether to
        skip or fail loudly.
        """
        deadline = time.monotonic() + max_wait
        last: Optional[str] = None
        path = f"/api/v4/item/media/{media_id}"
        while time.monotonic() < deadline:
            resp = self.raw("GET", path)
            if resp.status_code == 200:
                last = (resp.json() or {}).get("status")
                if last in want:
                    return last
                if last in self.MEDIA_TERMINAL_FAILURE:
                    raise RuntimeError(
                        f"media {media_id} reached terminal failure status {last!r} "
                        f"(wanted {want}); likely a transient download/source issue"
                    )
            time.sleep(interval)
        raise TimeoutError(
            f"status poll on {path}: wanted {want}, last seen {last!r} after {max_wait}s"
        )

    def poll_admin_domain_status(
        self,
        domain_id: str,
        want: set,
        max_wait: float = 300.0,
        interval: float = 2.0,
    ) -> str:
        return self._poll_status(
            f"/api/v4/admin/domain/{domain_id}",
            want,
            max_wait,
            interval,
        )

    def _poll_status(
        self, path: str, want: set, max_wait: float, interval: float
    ) -> str:
        deadline = time.monotonic() + max_wait
        last: Optional[str] = None
        while time.monotonic() < deadline:
            resp = self.raw("GET", path)
            if resp.status_code != 200:
                time.sleep(interval)
                continue
            last = (resp.json() or {}).get("status")
            if last in want:
                return last
            time.sleep(interval)
        raise TimeoutError(
            f"status poll on {path}: wanted {want}, last seen {last!r} after {max_wait}s"
        )
