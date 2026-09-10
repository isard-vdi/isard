# SPDX-License-Identifier: AGPL-3.0-or-later

"""Business-precondition guards of ``MediaService`` (services/media.py).

Covers the not-found / bad-request preconditions that, if they stopped firing,
would let a caller act on something they shouldn't:

* ``check_media_existence`` / ``delete_media`` -- unknown media -> not_found
  (and delete touches nothing).
* ``get_user_allowed_media`` -- unknown user -> not_found; unsupported sort
  field -> bad_sort_field.
* ``create_media`` -- a non-https / malformed URL -> media_url_bad_format; a URL
  that resolves internal -> media_url_internal.

The real service method decides; only the models / url validator are stubbed.
Asserts the ``description_code`` / ``Error`` type.
"""

from unittest.mock import patch

import pytest
from api.schemas.allowed import Allowed
from api.schemas.media import CreateMediaRequest
from api.services.error import Error
from api.services.media import MediaService


def _dc(exc):
    return exc.value.error["description_code"]


def _req(url="https://example.com/x.iso"):
    return CreateMediaRequest(
        name="testmedia",
        allowed=Allowed(),
        kind="iso",
        url=url,
        hypervisors_pools=["default"],
    )


# NOTE: check_media_existence's explicit "unknown media -> not_found" guard is
# intentionally NOT unit-tested: with exists() forced False, the RethinkMedia
# constructor right after it ALSO raises not_found for the missing row, so no
# single mutation of the explicit guard flips the outcome. delete_media below
# is distinguishable because it has an observable side effect to assert against.


class TestDeleteMedia:
    @patch("api.services.media.CommonMedia.remove_from_desktops")
    @patch("api.services.media.RethinkMedia.exists", return_value=False)
    def test_unknown_media_not_found_touches_nothing(self, _exists, remove):
        with pytest.raises(Error) as exc:
            MediaService.delete_media("ghost", {"user_id": "u1"})
        assert exc.value.error["error"] == "not_found"
        # A missing media must not trigger any desktop detach / file delete.
        remove.assert_not_called()


class TestGetUserAllowedMedia:
    @patch("api.services.media.RethinkUser.exists", return_value=False)
    def test_unknown_user_not_found(self, _exists):
        with pytest.raises(Error) as exc:
            MediaService.get_user_allowed_media("ghost", "cat", "grp", "user")
        assert exc.value.error["error"] == "not_found"

    @patch("api.services.media.RethinkUser.exists", return_value=True)
    def test_bad_sort_field_rejected(self, _exists):
        with pytest.raises(Error) as exc:
            MediaService.get_user_allowed_media(
                "u1", "cat", "grp", "user", sort_field="bogus"
            )
        assert _dc(exc) == "bad_sort_field"


class TestCreateMediaUrlGuards:
    def test_non_https_url_rejected(self):
        with pytest.raises(Error) as exc:
            MediaService.create_media(_req(url="http://example.com/x.iso"), {})
        assert _dc(exc) == "media_url_bad_format"

    def test_internal_url_rejected(self):
        with patch(
            "isardvdi_common.helpers.url_validation.validate_url_not_internal",
            side_effect=ValueError("URL resolves to internal address"),
        ):
            with pytest.raises(Error) as exc:
                MediaService.create_media(_req(), {})
        assert _dc(exc) == "media_url_internal"
