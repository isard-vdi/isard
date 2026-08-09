# SPDX-License-Identifier: AGPL-3.0-or-later

"""What ``DomainsHandler`` deletes on its way out, and what it forwards.

Three of its decisions destroy something or hide something, and none of
them had a test:

* the card image is deleted only when the row owns it. A shared default
  card carries the same shape, so widening that check removes an image
  every other desktop still points at;
* an empty deployment row is dropped only when nothing is left under the
  tag *and* the row is already on its way out. Either guard removed
  deletes a deployment somebody is still using;
* the frontend-status filter deliberately does not apply to deletes. A
  desktop whose last status was an engine-internal one would otherwise
  never be announced as gone, and the client would keep showing a row
  for a desktop that no longer exists.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _row(**attrs):
    base = dict(
        id="d1",
        name="desk",
        user="u1",
        category="cat1",
        kind="desktop",
        status="Stopped",
        tag=None,
        image=None,
    )
    base.update(attrs)
    return MagicMock(**base)


@pytest.fixture
def handler():
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    h = DomainsHandler(AsyncMock(), "domains")
    h.desktop_handler = MagicMock(
        on_insert=AsyncMock(), on_update=AsyncMock(), on_delete=AsyncMock()
    )
    h.template_handler = MagicMock(
        on_insert=AsyncMock(), on_update=AsyncMock(), on_delete=AsyncMock()
    )
    return h


# ---------------------------------------------------------------------------
# the card image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_a_user_uploaded_card_is_deleted(handler):
    """A built-in card is shared; deleting it blanks every desktop using it."""
    from isardvdi_change_handler.handlers import domains

    with patch.object(domains, "Cards") as cards:
        await handler.on_delete(_row(image={"type": "default", "id": "card-1"}))

    cards.delete_card.assert_not_called()


@pytest.mark.asyncio
async def test_a_user_uploaded_card_is_deleted(handler):
    from isardvdi_change_handler.handlers import domains

    with patch.object(domains, "Cards") as cards:
        await handler.on_delete(_row(image={"type": "user", "id": "card-1"}))

    cards.delete_card.assert_called_once_with("card-1")


@pytest.mark.asyncio
async def test_a_failed_card_delete_still_announces_the_desktop_is_gone(handler):
    """Fail open: the image is cosmetic, the delete event is not.

    Letting the card failure escape would skip the delegate, and the
    client would keep rendering a desktop that no longer exists.
    """
    from isardvdi_change_handler.handlers import domains

    with patch.object(domains, "Cards") as cards:
        cards.delete_card.side_effect = OSError("read-only fs")
        await handler.on_delete(_row(image={"type": "user", "id": "card-1"}))

    handler.desktop_handler.on_delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# the deployment cleanup
# ---------------------------------------------------------------------------


def _patch_rdb(remaining, deployment):
    """Stand in for the two rethink reads the cleanup performs.

    ``Deployment`` has to be patched alongside ``r``: ``_rdb_context``
    opens a real connection, and the driver error that raises is a
    ``ReqlError``, which this function's own except clause swallows. A
    test that patched only ``r`` would pass every "nothing was deleted"
    assertion without the body ever running.
    """
    from isardvdi_change_handler.handlers import domains

    table = MagicMock()
    table.get_all.return_value.count.return_value.run.return_value = remaining
    table.get.return_value.run.return_value = deployment
    rdb = MagicMock()
    rdb.table.return_value = table
    return (
        patch.object(domains, "r", rdb),
        patch.object(domains, "Deployment", MagicMock()),
        table,
    )


def test_a_deployment_with_desktops_left_is_not_deleted():
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    rdb_p, dep_p, table = _patch_rdb(remaining=2, deployment={"status": "deleting"})
    with rdb_p, dep_p:
        DomainsHandler._cleanup_deployment_if_empty("tag1")

    table.get.return_value.delete.assert_not_called()


def test_an_empty_deployment_not_already_deleting_is_left_alone():
    """The row is empty right now, but nobody asked for it to go - a
    deployment whose desktops were all removed by hand is still a
    deployment its owner expects to find."""
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    rdb_p, dep_p, table = _patch_rdb(remaining=0, deployment={"status": "started"})
    with rdb_p, dep_p:
        DomainsHandler._cleanup_deployment_if_empty("tag1")

    table.get.return_value.delete.assert_not_called()


def test_an_empty_deployment_already_deleting_is_dropped():
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    rdb_p, dep_p, table = _patch_rdb(remaining=0, deployment={"status": "deleting"})
    with rdb_p, dep_p:
        DomainsHandler._cleanup_deployment_if_empty("tag1")

    table.get.return_value.delete.return_value.run.assert_called_once()


def test_a_vanished_deployment_row_is_not_deleted():
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    rdb_p, dep_p, table = _patch_rdb(remaining=0, deployment=None)
    with rdb_p, dep_p:
        DomainsHandler._cleanup_deployment_if_empty("tag1")

    table.get.return_value.delete.assert_not_called()


def test_a_database_error_during_cleanup_is_swallowed():
    """Best effort: the caller's delete event must go out regardless."""
    from isardvdi_change_handler.handlers import domains
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    rdb = MagicMock()
    rdb.table.side_effect = domains.ReqlError("db down")

    with (
        patch.object(domains, "r", rdb),
        patch.object(domains, "Deployment", MagicMock()),
    ):
        DomainsHandler._cleanup_deployment_if_empty("tag1")


@pytest.mark.asyncio
async def test_only_a_tagged_desktop_triggers_the_deployment_cleanup(handler):
    """A template carries no deployment, and an untagged desktop has no
    deployment to empty - neither should pay for the rdb round trip."""
    from isardvdi_change_handler.handlers import domains

    with (
        patch.object(domains, "Cards"),
        patch.object(domains.DomainsHandler, "_cleanup_deployment_if_empty") as cleanup,
    ):
        await handler.on_delete(_row(tag=None))
        await handler.on_delete(_row(tag="tag1", kind="template", status="Stopped"))

    cleanup.assert_not_called()


# ---------------------------------------------------------------------------
# _delegate — the filter that must not apply to deletes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_engine_internal_status_is_not_forwarded_on_update(handler):
    from isardvdi_change_handler.handlers import domains

    with patch.object(
        domains.Helpers, "_is_frontend_desktop_status", return_value=False
    ):
        await handler.on_update(_row(), _row(status="ForceDeleting"))

    handler.desktop_handler.on_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_delete_is_forwarded_even_from_an_engine_internal_status(handler):
    """The status filter is for insert/update only. A desktop that died
    in a transactional status is still a desktop the client must be told
    about, or its row never disappears."""
    from isardvdi_change_handler.handlers import domains

    with (
        patch.object(domains, "Cards"),
        patch.object(
            domains.Helpers, "_is_frontend_desktop_status", return_value=False
        ),
    ):
        await handler.on_delete(_row(status="ForceDeleting"))

    handler.desktop_handler.on_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_template_row_goes_to_the_template_handler(handler):
    from isardvdi_change_handler.handlers import domains

    with patch.object(
        domains.Helpers, "_is_frontend_desktop_status", return_value=True
    ):
        await handler.on_insert(_row(kind="template"))

    handler.template_handler.on_insert.assert_awaited_once()
    handler.desktop_handler.on_insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unknown_kind_is_dropped_rather_than_guessed(handler):
    from isardvdi_change_handler.handlers import domains

    with patch.object(
        domains.Helpers, "_is_frontend_desktop_status", return_value=True
    ):
        await handler.on_insert(_row(kind="something_else"))

    handler.desktop_handler.on_insert.assert_not_awaited()
    handler.template_handler.on_insert.assert_not_awaited()
