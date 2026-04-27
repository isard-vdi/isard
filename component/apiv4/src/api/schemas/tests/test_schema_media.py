# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/media.py``."""

import pytest
from api.schemas.media import (
    CreateMediaRequest,
    DesktopAttachedMediaItem,
    MediaCheckResponse,
    MediaInstallItem,
    MediaItemResponse,
    MediaProgress,
    MediaQuotaCheckResponse,
    MediaResponse,
    MediaUser,
    UserMediaResponse,
    UserSharedMedia,
    UserSharedMediaResponse,
)
from pydantic import ValidationError


class TestCreateMediaRequest:
    _valid = {
        "name": "Ubuntu 24.04 ISO",
        "allowed": {},
        "kind": "iso",
        "url": "https://example.com/ubuntu.iso",
        "hypervisors_pools": ["default"],
    }

    def test_accepts_required(self):
        r = CreateMediaRequest(**self._valid)
        assert r.name == "Ubuntu 24.04 ISO"
        assert r.description == ""

    def test_name_min_length_4(self):
        """min_length=4 — pin so a too-short name is rejected."""
        with pytest.raises(ValidationError):
            CreateMediaRequest(**{**self._valid, "name": "x"})

    def test_name_max_length_50(self):
        with pytest.raises(ValidationError):
            CreateMediaRequest(**{**self._valid, "name": "x" * 51})

    def test_description_max_length_255(self):
        with pytest.raises(ValidationError):
            CreateMediaRequest(**{**self._valid, "description": "x" * 256})

    def test_url_must_be_http(self):
        """url is HttpUrl — Pydantic rejects non-http schemes."""
        with pytest.raises(ValidationError):
            CreateMediaRequest(**{**self._valid, "url": "javascript:alert(1)"})

    def test_url_invalid_format_rejected(self):
        with pytest.raises(ValidationError):
            CreateMediaRequest(**{**self._valid, "url": "not a url"})

    def test_kind_enum_rejected_invalid(self):
        with pytest.raises(ValidationError):
            CreateMediaRequest(**{**self._valid, "kind": "movie"})


class TestMediaResponse:
    _required = {
        "id": "m-1",
        "name": "Media",
        "category": "default",
        "allowed": {},
        "description": "x",
        "status": "Downloaded",
        "user": "u-1",
        "username": "u",
        "kind": "iso",
    }

    def test_accepts_required(self):
        r = MediaResponse(**self._required)
        assert r.kind == "iso"
        assert r.accessed is None
        assert r.group is None

    def test_status_enum_rejects_invalid(self):
        with pytest.raises(ValidationError):
            MediaResponse(**{**self._required, "status": "BogusStatus"})


class TestMediaProgress:
    """All defaults — pin so a partial / missing progress dict still
    validates (legacy rows + freshly-inserted media)."""

    def test_all_defaults(self):
        p = MediaProgress()
        assert p.received == "0"
        assert p.received_percent == 0
        assert p.total == ""
        assert p.total_percent == 0
        assert p.speed_current == ""
        assert p.speed_download_average == ""

    def test_partial_overrides(self):
        p = MediaProgress(received="100", received_percent=50)
        assert p.received_percent == 50


class TestMediaItemResponse:
    """Includes a `progress` field with custom default-from-None
    validator — pin both the alias-based field names and the
    None-coerces-to-empty-dict logic."""

    _payload = {
        "id": "m-1",
        "name": "Media",
        "description": "x",
        "kind": "iso",
        "url-isard": "https://x/i",
        "url-web": "https://x/w",
        "status": "Downloaded",
        "user": "u-1",
        "category": "default",
        "group": "default-default",
        "accessed": 1234567890.0,
        "icon": "iso",
        "editable": True,
    }

    def test_alias_fields(self):
        """``url-isard`` and ``url-web`` use validation_alias — RethinkDB
        column names with hyphens map to Python identifiers."""
        r = MediaItemResponse(**self._payload)
        assert r.url_isard == "https://x/i"
        assert r.url_web == "https://x/w"

    def test_progress_none_defaults_to_empty(self):
        """The custom @field_validator coerces None → {} so the schema
        stays valid for rows where the engine hasn't populated progress
        yet. Pin the validator so a future refactor doesn't drop it
        and crash the entire /items/media response."""
        r = MediaItemResponse(**{**self._payload, "progress": None})
        # Empty dict triggers MediaProgress defaults.
        assert r.progress.received == "0"

    def test_progress_dict_passes(self):
        r = MediaItemResponse(**{**self._payload, "progress": {"received_percent": 42}})
        assert r.progress.received_percent == 42


class TestMediaQuotaCheckResponse:
    """Empty body — pin so a future field add is intentional."""

    def test_empty(self):
        assert MediaQuotaCheckResponse().model_dump() == {}


class TestDesktopAttachedMediaItem:
    _required = {"id": "m-1", "name": "M", "kind": "iso"}

    def test_kind_literal(self):
        """kind is Literal['iso', 'floppy'] — anything else fails."""
        DesktopAttachedMediaItem(**self._required)
        DesktopAttachedMediaItem(**{**self._required, "kind": "floppy"})
        with pytest.raises(ValidationError):
            DesktopAttachedMediaItem(**{**self._required, "kind": "cdrom"})

    def test_size_optional(self):
        r = DesktopAttachedMediaItem(**self._required)
        assert r.size is None


class TestMediaCheckResponse:
    def test_default_task_id_none(self):
        """task_id=None means "no task queued" (the no-op happy path).
        Pin so a future change that returns {} doesn't break callers
        that check `response.task_id is None`."""
        r = MediaCheckResponse()
        assert r.task_id is None


class TestMediaInstallItem:
    _required = {"id": "ubuntu-24-04", "name": "Ubuntu 24.04"}

    def test_accepts_required(self):
        r = MediaInstallItem(**self._required)
        assert r.description == ""
        assert r.vers is None

    def test_extra_keys_allowed(self):
        """class Config: extra = 'allow' — full DB row passes through.
        Pin so a refactor that flips to extra='ignore' is loud."""
        r = MediaInstallItem(**self._required, extra_field="xyz")
        assert r.model_dump()["extra_field"] == "xyz"


class TestMediaUser:
    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_required(self, missing):
        payload = {"id": "u-1", "name": "U"}
        del payload[missing]
        with pytest.raises(ValidationError):
            MediaUser(**payload)


class TestUserSharedMedia:
    _required = {
        "id": "m-1",
        "name": "Media",
        "accessed": 1234567890.0,
        "kind": "iso",
        "status": "Downloaded",
    }

    def test_accepts_required(self):
        m = UserSharedMedia(**self._required)
        assert m.description is None
        assert m.user is None

    def test_progress_default_factory(self):
        """progress uses default_factory=MediaProgress — each instance
        gets its own."""
        a = UserSharedMedia(**self._required)
        b = UserSharedMedia(**self._required)
        assert a.progress is not b.progress

    def test_progress_none_coerced(self):
        """Same @field_validator as MediaItemResponse."""
        m = UserSharedMedia(**{**self._required, "progress": None})
        assert m.progress.received == "0"


class TestUserMediaResponse:
    def test_media_required(self):
        with pytest.raises(ValidationError):
            UserMediaResponse()


class TestUserSharedMediaResponse:
    def test_media_required(self):
        with pytest.raises(ValidationError):
            UserSharedMediaResponse()

    def test_accepts_empty(self):
        assert UserSharedMediaResponse(media=[]).media == []
