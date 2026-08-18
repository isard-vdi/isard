# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestDomainsOnUpdate:
    """Test DesktopDomainHandler.on_update progress-stripping logic."""

    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.domains import DesktopDomainHandler

        sio = AsyncMock()
        h = DesktopDomainHandler(sio)
        # Short-circuit on_update by forcing the owner-changed branch, which
        # calls on_delete/on_insert (mocked) and returns immediately after
        # enrichment.
        h.on_delete = AsyncMock()
        h.on_insert = AsyncMock()
        return h

    @pytest.mark.asyncio
    async def test_strips_unchanged_progress(self, handler):
        """When old and new have the same progress, on_update should clear it on new_val."""
        old = FakeRow(
            kind="desktop",
            status="Started",
            user="u1",
            additional_properties={"progress": {"received": 50}},
        )
        new = FakeRow(
            kind="desktop",
            status="Started",
            user="u2",
            additional_properties={"progress": {"received": 50}},
        )
        await handler.on_update(old, new)

        handler.on_insert.assert_awaited_once()
        updated_new = handler.on_insert.call_args[0][0]
        dumped = updated_new.model_dump()
        assert dumped.get("progress") is None

    @pytest.mark.asyncio
    async def test_keeps_changed_progress(self, handler):
        """When progress changed, it should be preserved."""
        old = FakeRow(
            kind="desktop",
            status="Started",
            user="u1",
            additional_properties={"progress": {"received": 50}},
        )
        new = FakeRow(
            kind="desktop",
            status="Started",
            user="u2",
            additional_properties={"progress": {"received": 80}},
        )
        await handler.on_update(old, new)

        handler.on_insert.assert_awaited_once()
        updated_new = handler.on_insert.call_args[0][0]
        dumped = updated_new.model_dump()
        assert dumped.get("progress") == {"received": 80}


class TestDomainsDelegate:
    """Test the _delegate method which routes to desktop or template handlers."""

    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        sio = AsyncMock()
        h = DomainsHandler(sio, "domains")
        h.desktop_handler = AsyncMock()
        h.template_handler = AsyncMock()
        return h

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    async def test_delegate_insert_desktop(self, mock_status, handler):
        new_val = FakeRow(kind="desktop", status="Started", user="u1")
        await handler._delegate("on_insert", new_val)
        handler.desktop_handler.on_insert.assert_awaited_once_with(new_val)

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    async def test_delegate_insert_template(self, mock_status, handler):
        new_val = FakeRow(kind="template", status="Stopped", user="u1")
        await handler._delegate("on_insert", new_val)
        handler.template_handler.on_insert.assert_awaited_once_with(new_val)

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    async def test_delegate_update(self, mock_status, handler):
        old = FakeRow(kind="desktop", status="Stopped", user="u1")
        new = FakeRow(kind="desktop", status="Started", user="u1")
        await handler._delegate("on_update", old, new)
        handler.desktop_handler.on_update.assert_awaited_once_with(old, new)

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    async def test_delegate_delete(self, mock_status, handler):
        old = FakeRow(kind="desktop", status="Stopped", user="u1")
        await handler._delegate("on_delete", old)
        handler.desktop_handler.on_delete.assert_awaited_once_with(old)

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=False,
    )
    async def test_delegate_skips_engine_status(self, mock_status, handler):
        """Engine-transactional statuses should not be forwarded."""
        new_val = FakeRow(kind="desktop", status="CreatingDisk", user="u1")
        await handler._delegate("on_insert", new_val)
        handler.desktop_handler.on_insert.assert_not_awaited()
        handler.template_handler.on_insert.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    async def test_delegate_insert_uses_new_val_for_kind(self, mock_status, handler):
        """on_insert passes new_val as positional old_val — _delegate must handle this."""
        new_val = FakeRow(kind="template", status="Stopped", user="u1")
        await handler._delegate("on_insert", new_val)
        handler.template_handler.on_insert.assert_awaited_once()


@pytest.mark.asyncio
@patch(
    "isardvdi_change_handler.handlers.domains.DesktopsProcessed._parse_desktop",
    side_effect=lambda d: d,
)
async def test_desktop_owner_change_does_not_double_emit(
    mock_parse, desktop_handler, fake_socketio, domain_row_factory
):
    old_val = domain_row_factory(
        id="d1", user="alice", status="Started", kind="desktop"
    )
    new_val = domain_row_factory(id="d1", user="bob", status="Started", kind="desktop")

    await desktop_handler.on_update(old_val, new_val)

    events = [e[0] for e in fake_socketio.emitted]
    assert events.count("desktop_delete") >= 1
    assert events.count("desktop_add") >= 1
    assert (
        "desktop_update" not in events
    ), f"owner-change path must not also emit desktop_update; got {events}"


@pytest.mark.asyncio
@patch("isardvdi_change_handler.handlers.domains.Logging")
@patch("isardvdi_change_handler.handlers.domains.Scheduler")
@patch(
    "isardvdi_change_handler.handlers.domains.DesktopsProcessed._parse_desktop",
    side_effect=lambda d: d,
)
async def test_on_update_strips_start_logs_id_from_emitted_payload(
    mock_parse,
    mock_scheduler,
    mock_logging,
    desktop_handler,
    fake_socketio,
    domain_row_factory,
):
    """Regression: start_logs_id is internal (used to call Logging.*) and
    must not be emitted to /administrators or /userspace."""
    old_val = domain_row_factory(
        id="d-1",
        user="u-1",
        category="cat-a",
        status="Started",
        additional_properties={"progress": 100},
    )
    new_val = domain_row_factory(
        id="d-1",
        user="u-1",
        category="cat-a",
        status="Stopped",
        additional_properties={"progress": 100, "start_logs_id": "log-42"},
    )
    await desktop_handler.on_update(old_val, new_val)

    for event, payload, namespace, room in fake_socketio.emitted:
        assert (
            "start_logs_id" not in payload
        ), f"event {event!r} to {namespace} leaked start_logs_id: {payload}"


@pytest.mark.asyncio
async def test_on_update_skips_when_domain_deleted(
    monkeypatch, desktop_handler, fake_socketio, domain_row_factory
):
    """Regression (#2074): under create/delete churn the domains changefeed can
    deliver an update for a domain already deleted; get_domain_enrichment then
    returns None. on_update must skip quietly and emit nothing, not crash on
    ap.update(None)."""
    monkeypatch.setattr(
        "isardvdi_common.lib.domains.desktops.desktops.DesktopsProcessed.get_domain_enrichment",
        staticmethod(lambda _id: None),
    )
    old_val = domain_row_factory(id="d-gone", status="Started")
    new_val = domain_row_factory(id="d-gone", status="Stopped")

    await desktop_handler.on_update(old_val, new_val)

    assert (
        fake_socketio.emitted == []
    ), f"deleted-domain update must emit nothing; got {fake_socketio.emitted}"


class TestDomainsNoneRoomRegression:
    """Regression: DesktopDomainHandler.emit / TemplateDomainHandler.emit must
    refuse to forward with room=None (would broadcast to the whole namespace)."""

    @pytest.mark.asyncio
    async def test_desktop_domain_emit_skips_when_room_is_none(self):
        from isardvdi_change_handler.handlers.domains import DesktopDomainHandler

        sio = AsyncMock()
        h = DesktopDomainHandler(sio)
        await h.emit("desktop_data", "{}", namespace="/administrators", room=None)
        sio.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_template_domain_emit_skips_when_room_is_none(self):
        from isardvdi_change_handler.handlers.domains import TemplateDomainHandler

        sio = AsyncMock()
        h = TemplateDomainHandler(sio)
        await h.emit("template_data", "{}", namespace="/administrators", room=None)
        sio.emit.assert_not_called()


class TestDomainsHandlerOnDelete:
    """Pin the asyncio.to_thread offload of the deployment-cleanup
    rdb work in ``DomainsHandler.on_delete``.

    Before the offload, ``on_delete`` ran three rdb queries
    (count + get + delete) on the event-loop thread, freezing every
    other handler in the process for the duration. After the
    offload the rdb work runs in a worker thread; the handler's
    asyncio context is free between calls.
    """

    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        sio = AsyncMock()
        h = DomainsHandler(sio, "domains")
        h.desktop_handler = AsyncMock()
        h.desktop_handler.on_delete = AsyncMock()
        h.template_handler = AsyncMock()
        return h

    @pytest.mark.asyncio
    async def test_cleanup_runs_off_event_loop(self, handler):
        """Smoking-gun assertion: the rdb cleanup is invoked through
        ``asyncio.to_thread``. Patching the cleanup to a sync function
        with a synchronous side-effect AND patching ``asyncio.to_thread``
        lets us assert the dispatch goes through to_thread (and so
        the event loop is free during the call)."""
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        called = []

        def fake_cleanup(tag):
            called.append(tag)

        with patch.object(
            DomainsHandler,
            "_cleanup_deployment_if_empty",
            staticmethod(fake_cleanup),
        ), patch("isardvdi_change_handler.handlers.domains.asyncio") as fake_asyncio:
            # Make to_thread an awaitable that records its target
            scheduled = []

            async def fake_to_thread(fn, *args, **kwargs):
                scheduled.append((fn, args))
                fn(*args, **kwargs)
                return None

            fake_asyncio.to_thread = fake_to_thread

            old_val = FakeRow(
                kind="desktop",
                status="Stopped",
                user="u1",
                tag="deploy-1",
                image=None,
            )
            await handler.on_delete(old_val)

            assert called == ["deploy-1"], "cleanup must run with the deployment tag"
            assert (
                len(scheduled) == 1
            ), "cleanup must dispatch through asyncio.to_thread (not call sync)"
            assert scheduled[0][1] == ("deploy-1",)

        # Delegate must always run after the cleanup, regardless of
        # whether the cleanup found anything to delete.
        handler.desktop_handler.on_delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_cleanup_when_no_tag(self, handler):
        """Tagless desktops skip the rdb cleanup entirely — there's
        no deployment to potentially delete."""
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        with patch.object(
            DomainsHandler, "_cleanup_deployment_if_empty"
        ) as fake_cleanup:
            old_val = FakeRow(
                kind="desktop",
                status="Stopped",
                user="u1",
                tag=None,
                image=None,
            )
            await handler.on_delete(old_val)

            fake_cleanup.assert_not_called()

        handler.desktop_handler.on_delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_cleanup_when_template(self, handler):
        """Template deletes never have a tag and never need cleanup."""
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        with patch.object(
            DomainsHandler, "_cleanup_deployment_if_empty"
        ) as fake_cleanup:
            old_val = FakeRow(
                kind="template",
                status="Stopped",
                user="u1",
                tag="never-set-on-templates",
                image=None,
            )
            await handler.on_delete(old_val)

            # Templates skip the deployment-cleanup branch — kind != "desktop".
            fake_cleanup.assert_not_called()

        handler.template_handler.on_delete.assert_awaited_once()


class TestCleanupDeploymentIfEmpty:
    """Drive the sync helper directly through a stubbed _rdb_context
    + r.table chain. Pin the three branches: remaining > 0 (no
    delete); remaining == 0 + status != deleting (no delete);
    remaining == 0 + status == deleting (delete fires).
    """

    @pytest.fixture
    def stub_rdb(self, monkeypatch):
        from unittest.mock import MagicMock

        from isardvdi_change_handler.handlers import domains as mod

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        # Override the _rdb_context that the helper acquires.
        monkeypatch.setattr(
            mod.Deployment,
            "_rdb_context",
            classmethod(lambda cls: _Ctx()),
        )
        monkeypatch.setattr(
            type(mod.Deployment),
            "_rdb_connection",
            property(lambda self: MagicMock(name="conn")),
        )
        mock_table = MagicMock(name="r.table")
        monkeypatch.setattr(mod.r, "table", mock_table)
        return mock_table

    def test_skips_delete_when_remaining_desktops(self, stub_rdb):
        """Count returns nonzero → no get/delete fires."""
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        # First .run() (the count) returns 5 (remaining desktops).
        stub_rdb.return_value.get_all.return_value.count.return_value.run.return_value = (
            5
        )

        DomainsHandler._cleanup_deployment_if_empty("deploy-1")

        # The deployment-row delete chain must NOT have fired.
        stub_rdb.return_value.get.return_value.delete.assert_not_called()

    def test_skips_delete_when_status_not_deleting(self, stub_rdb):
        """Empty deployment but status != 'deleting' → leave it alone."""
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        stub_rdb.return_value.get_all.return_value.count.return_value.run.return_value = (
            0
        )
        stub_rdb.return_value.get.return_value.run.return_value = {
            "id": "deploy-1",
            "status": "active",
        }

        DomainsHandler._cleanup_deployment_if_empty("deploy-1")

        stub_rdb.return_value.get.return_value.delete.assert_not_called()

    def test_deletes_empty_deployment_in_deleting_status(self, stub_rdb):
        """Empty + status='deleting' → delete fires."""
        from isardvdi_change_handler.handlers.domains import DomainsHandler

        stub_rdb.return_value.get_all.return_value.count.return_value.run.return_value = (
            0
        )
        stub_rdb.return_value.get.return_value.run.return_value = {
            "id": "deploy-1",
            "status": "deleting",
        }

        DomainsHandler._cleanup_deployment_if_empty("deploy-1")

        stub_rdb.return_value.get.return_value.delete.assert_called_once()


class TestWireguardMacCacheInvalidation:
    """The stopped branch of ``on_update`` must drop the desktop's wg MAC entry.

    ``wg_mac_domain_cache`` is keyed by wireguard MAC, but this handler only
    ever holds a domain id, so invalidating through the MAC-keyed helper
    matched nothing and the mapping stayed until its TTL expired.
    """

    WG_MAC = "52:54:00:2c:7a:13"

    @pytest.fixture(autouse=True)
    def clean_cache(self):
        from isardvdi_common.helpers.caches import Caches

        Caches.wg_mac_domain_cache.clear()
        yield
        Caches.wg_mac_domain_cache.clear()

    @pytest.fixture
    def stub_scheduler(self, monkeypatch):
        monkeypatch.setattr(
            "isardvdi_change_handler.handlers.domains.Scheduler.remove_desktop_timeouts",
            staticmethod(lambda _id: None),
        )

    @staticmethod
    def _wireguard_hardware(mac):
        return {"hardware": {"interfaces": [{"id": "wireguard", "mac": mac}]}}

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.DesktopsProcessed._parse_desktop",
        side_effect=lambda d: d,
    )
    async def test_stop_drops_the_mapping_the_start_cached(
        self, mock_parse, stub_scheduler, desktop_handler, domain_row_factory
    ):
        """Round-trip through the handler: Starting->Started caches, Started->Stopped drops."""
        from isardvdi_common.helpers.caches import Caches

        starting = domain_row_factory(id="d1", status="Starting")
        started = domain_row_factory(
            id="d1",
            status="Started",
            create_dict=self._wireguard_hardware(self.WG_MAC),
        )
        await desktop_handler.on_update(starting, started)
        assert Caches.wg_mac_domain_cache[self.WG_MAC] == "d1"

        stopped = domain_row_factory(id="d1", status="Stopped")
        await desktop_handler.on_update(started, stopped)

        assert self.WG_MAC not in Caches.wg_mac_domain_cache

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.DesktopsProcessed._parse_desktop",
        side_effect=lambda d: d,
    )
    async def test_stop_leaves_another_desktops_mapping_alone(
        self, mock_parse, stub_scheduler, desktop_handler, domain_row_factory
    ):
        from isardvdi_common.helpers.caches import Caches

        other_mac = "52:54:00:aa:bb:cc"
        Caches.wg_mac_domain_cache[self.WG_MAC] = "d1"
        Caches.wg_mac_domain_cache[other_mac] = "d2"

        started = domain_row_factory(
            id="d1",
            status="Started",
            create_dict=self._wireguard_hardware(self.WG_MAC),
        )
        stopped = domain_row_factory(id="d1", status="Stopped")
        await desktop_handler.on_update(started, stopped)

        assert self.WG_MAC not in Caches.wg_mac_domain_cache
        assert Caches.wg_mac_domain_cache[other_mac] == "d2"


class TestDirectViewerStatusNormalisation:
    """The direct viewer room must carry the same parsed status desktop_update does."""

    @staticmethod
    def _parse_desktop_stub(desktop):
        from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed

        return {
            **desktop,
            "status": DesktopsProcessed.parse_frontend_desktop_status(dict(desktop))[
                "status"
            ],
        }

    @staticmethod
    def _viewer_statuses(fake_socketio):
        import json

        return [
            json.loads(payload)["status"]
            for event, payload, _ns, _room in fake_socketio.emitted
            if event == "directviewer_update"
        ]

    @pytest.mark.asyncio
    @patch("isardvdi_change_handler.handlers.domains.Logging")
    @patch("isardvdi_change_handler.handlers.domains.Scheduler")
    async def test_collapses_engine_internal_status(
        self,
        _scheduler,
        _logging,
        desktop_handler,
        fake_socketio,
        domain_row_factory,
    ):
        with patch(
            "isardvdi_change_handler.handlers.domains.DesktopsProcessed._parse_desktop",
            side_effect=self._parse_desktop_stub,
        ):
            await desktop_handler.on_update(
                domain_row_factory(
                    id="d1", status="Stopped", additional_properties={"jumperurl": "tk"}
                ),
                domain_row_factory(
                    id="d1",
                    status="CreatingDisk",
                    additional_properties={"jumperurl": "tk"},
                ),
            )

        assert self._viewer_statuses(fake_socketio) == ["Creating"]

    @pytest.mark.asyncio
    @patch("isardvdi_change_handler.handlers.domains.Logging")
    @patch("isardvdi_change_handler.handlers.domains.Scheduler")
    async def test_emits_when_only_the_parsed_status_changes(
        self,
        _scheduler,
        _logging,
        desktop_handler,
        fake_socketio,
        domain_row_factory,
    ):
        """Started without a viewer password parses as Starting; when the password
        lands the raw status is unchanged, so only the parsed comparison fires."""
        no_passwd = domain_row_factory(
            id="d1",
            status="Started",
            additional_properties={"jumperurl": "tk", "viewer": {}},
        )
        with_passwd = domain_row_factory(
            id="d1",
            status="Started",
            additional_properties={"jumperurl": "tk", "viewer": {"passwd": "p"}},
        )

        with patch(
            "isardvdi_change_handler.handlers.domains.DesktopsProcessed._parse_desktop",
            side_effect=self._parse_desktop_stub,
        ):
            await desktop_handler.on_update(
                domain_row_factory(
                    id="d1", status="Stopped", additional_properties={"jumperurl": "tk"}
                ),
                no_passwd,
            )
            await desktop_handler.on_update(no_passwd, with_passwd)

        assert self._viewer_statuses(fake_socketio) == ["Starting", "Started"]
