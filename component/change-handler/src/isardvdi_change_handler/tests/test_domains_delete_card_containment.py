# SPDX-License-Identifier: AGPL-3.0-or-later

"""A failing card delete must not take the rest of ``on_delete`` with it.

``on_delete`` does three things for a deleted desktop, in this order: remove
the user-uploaded card file, drop the deployment row when its last desktop is
gone, and forward the deletion to the socketio handler -- which is what tells
the client the desktop no longer exists.

The card step used to catch only ``(OSError, KeyError)``. Anything else escaped
and ``BaseHandler`` logged it as "skipping", so the two steps after it never
ran: a deployment stuck in ``deleting`` stayed, and the browser kept showing a
desktop that was already gone.

That was not hypothetical. ``Cards`` resolves its paths at import time inside an
``if``/``elif`` on where the ``api`` module lives, with no ``else``, so in the
change-handler process ``USERS_CARDS`` is undefined and ``delete_card`` raises
``NameError`` on every call.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow

_CARD = {"id": "desktop-1.jpg", "type": "user"}


@pytest.fixture
def handler():
    from isardvdi_change_handler.handlers.domains import DomainsHandler

    h = DomainsHandler(AsyncMock(), "domains")
    h.desktop_handler = AsyncMock()
    h.template_handler = AsyncMock()
    return h


def _desktop():
    return FakeRow(
        id="desktop-1",
        kind="desktop",
        status="Stopped",
        user="u1",
        tag="deployment-1",
        image=_CARD,
    )


class TestCardDeleteFailureIsContained:
    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    @patch(
        "isardvdi_change_handler.handlers.domains.Cards.delete_card",
        side_effect=NameError("name 'USERS_CARDS' is not defined"),
    )
    async def test_a_nameerror_still_leaves_the_deployment_cleaned(
        self, _card, _status, handler
    ):
        cleanup = Mock()
        handler._cleanup_deployment_if_empty = cleanup

        await handler.on_delete(_desktop())

        cleanup.assert_called_once_with("deployment-1")

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    @patch(
        "isardvdi_change_handler.handlers.domains.Cards.delete_card",
        side_effect=NameError("name 'USERS_CARDS' is not defined"),
    )
    async def test_a_nameerror_still_emits_the_deletion(self, _card, _status, handler):
        """The one the user sees: without this the desktop stays on screen."""
        handler._cleanup_deployment_if_empty = Mock()

        await handler.on_delete(_desktop())

        handler.desktop_handler.on_delete.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    @patch(
        "isardvdi_change_handler.handlers.domains.Cards.delete_card",
        side_effect=OSError("disk gone"),
    )
    async def test_the_errors_already_caught_keep_being_caught(
        self, _card, _status, handler
    ):
        """The narrow cases must not regress while widening the clause."""
        handler._cleanup_deployment_if_empty = Mock()

        await handler.on_delete(_desktop())

        handler.desktop_handler.on_delete.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.domains.Helpers._is_frontend_desktop_status",
        return_value=True,
    )
    @patch("isardvdi_change_handler.handlers.domains.Cards.delete_card")
    async def test_the_happy_path_is_unchanged(self, card, _status, handler):
        """A card that deletes cleanly is still deleted, and once."""
        handler._cleanup_deployment_if_empty = Mock()

        await handler.on_delete(_desktop())

        card.assert_called_once_with("desktop-1.jpg")
        handler.desktop_handler.on_delete.assert_awaited_once()
