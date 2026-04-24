# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for MediaService — the route-callable façade over CommonMedia
+ Alloweds. Tests pin the not-found dispatch and the simple delegate
patterns.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.media import MediaService


class TestGetMedia:
    @patch(
        "api.services.media.CommonMedia.get_info",
        return_value={"id": "m1", "name": "iso"},
    )
    @patch("api.services.media.RethinkMedia.exists", return_value=True)
    def test_returns_info_when_present(self, _exists, mock_info):
        result = MediaService.get_media("m1")
        mock_info.assert_called_once_with("m1")
        assert result == {"id": "m1", "name": "iso"}

    @patch("api.services.media.RethinkMedia.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            MediaService.get_media("ghost")


class TestGetUserMedia:
    @patch("api.services.media.CommonMedia.get_user_media", return_value=["m1"])
    def test_passes_user_id_through(self, mock_get):
        assert MediaService.get_user_media("u1") == ["m1"]
        mock_get.assert_called_once_with("u1")


class TestGetUserSharedMedia:
    @patch("api.services.media.Alloweds.get_items_allowed", return_value=[])
    @patch("api.services.media.RethinkUser.exists", return_value=True)
    def test_calls_alloweds_with_only_in_allowed(self, _exists, mock_alloweds):
        payload = {"user_id": "u1", "category_id": "default"}
        MediaService.get_user_shared_media(payload)
        kwargs = mock_alloweds.call_args.kwargs
        assert kwargs["only_in_allowed"] is True
        assert kwargs["order"] == "name"

    @patch("api.services.media.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_missing_user(self, _exists):
        with pytest.raises(Error):
            MediaService.get_user_shared_media({"user_id": "ghost"})


class TestGetMediaAllowed:
    @patch(
        "api.services.media.Alloweds.get_allowed_groups",
        return_value=[{"id": "g1"}],
    )
    @patch(
        "api.services.media.RethinkMedia.get",
        return_value={"allowed": {"groups": ["g1"]}},
    )
    @patch("api.services.media.RethinkMedia.exists", return_value=True)
    def test_returns_selected_and_available_groups(self, _exists, _get, _alloweds):
        result = MediaService.get_media_allowed("m1", "default")
        assert result == {
            "selected": {"groups": ["g1"]},
            "available_groups": [{"id": "g1"}],
        }

    @patch("api.services.media.RethinkMedia.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            MediaService.get_media_allowed("ghost", "default")
