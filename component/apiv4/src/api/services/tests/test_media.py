# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for MediaService — the route-callable façade over CommonMedia
+ Alloweds. Tests pin the not-found dispatch and the simple delegate
patterns.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests
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


class TestCreateMediaUrlProbe:
    """Pin the URL-probe contract used by ``MediaService.create_media``.

    The earlier urllib-based probe wedged the apiv4 event loop the
    one time archive.org stalled mid-handshake — the retry path was
    declared without a ``timeout`` so it could hang forever, and the
    request handler is ``async def`` so a single hung probe blocks
    every other in-flight request. The fix replaces urllib with
    ``requests.get(stream=True, timeout=30)`` (both attempts) and
    moves the service call to the threadpool. These tests pin the
    error mapping and — critically — that **every** outbound
    ``requests.get`` is bounded by ``timeout=30``.
    """

    _PAYLOAD = {
        "user_id": "u1",
        "category_id": "default",
        "group_id": "default-default",
        "provider": "local",
    }

    @staticmethod
    def _media_data(url="https://example.com/iso.iso"):
        from api.schemas.media import CreateMediaRequest

        return CreateMediaRequest.model_validate(
            {
                "name": "media-name",
                "description": "",
                "kind": "iso",
                "url": url,
                "hypervisors_pools": ["default"],
                "allowed": {
                    "users": False,
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            }
        )

    def _make_response(self, status_code=200, content_length="42"):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = status_code
        resp.headers = {"Content-Length": content_length} if content_length else {}
        return resp

    @patch("isardvdi_common.helpers.url_validation.validate_url_not_internal")
    @patch("api.services.media.requests.get")
    def test_404_maps_to_media_url_not_found(self, mock_get, _validate):
        mock_get.return_value = self._make_response(status_code=404)
        with pytest.raises(Error) as exc_info:
            MediaService.create_media(self._media_data(), self._PAYLOAD)
        assert exc_info.value.error["description_code"] == "media_url_not_found"

    @patch("isardvdi_common.helpers.url_validation.validate_url_not_internal")
    @patch("api.services.media.requests.get")
    def test_request_exception_maps_to_url_not_valid(self, mock_get, _validate):
        # ``requests.Timeout`` is the canonical class for the
        # "remote stalled past our timeout" case the original urllib
        # path could hang on indefinitely.
        mock_get.side_effect = requests.Timeout("simulated stall")
        with pytest.raises(Error) as exc_info:
            MediaService.create_media(self._media_data(), self._PAYLOAD)
        assert exc_info.value.error["description_code"] == "media_url_not_valid"

    @patch("isardvdi_common.helpers.url_validation.validate_url_not_internal")
    @patch("api.services.media.requests.get")
    def test_403_then_failure_retries_with_mozilla_ua_and_keeps_timeout(
        self, mock_get, _validate
    ):
        first = self._make_response(status_code=403)
        second = self._make_response(status_code=403)
        mock_get.side_effect = [first, second]
        with pytest.raises(Error) as exc_info:
            MediaService.create_media(self._media_data(), self._PAYLOAD)
        assert exc_info.value.error["description_code"] == "media_url_not_valid"

        assert mock_get.call_count == 2
        for call in mock_get.call_args_list:
            assert call.kwargs.get("timeout") == 30, (
                "every probe attempt MUST carry timeout=30; the prior "
                "urllib retry passed no timeout and could wedge the "
                "apiv4 event loop indefinitely"
            )
            assert call.kwargs.get("stream") is True, (
                "probe must use stream=True so we don't download the "
                "whole upstream body just to read its size"
            )
        retry_headers = mock_get.call_args_list[1].kwargs.get("headers") or {}
        assert "Mozilla" in retry_headers.get("User-Agent", "")
