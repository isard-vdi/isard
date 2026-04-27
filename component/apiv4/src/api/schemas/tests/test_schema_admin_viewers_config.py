# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_viewers_config.py``."""

from api.schemas.admin_viewers_config import ViewerConfigUpdateRequest


class TestViewerConfigUpdateRequest:
    def test_accepts_string(self):
        r = ViewerConfigUpdateRequest(custom="title=spice")
        assert r.custom == "title=spice"

    def test_accepts_none(self):
        """custom=None is the legitimate "clear the override" value —
        the route uses it to wipe the per-viewer custom block. Pin
        so a future schema change that disallows None is noticed."""
        r = ViewerConfigUpdateRequest(custom=None)
        assert r.custom is None

    def test_accepts_empty(self):
        """Optional with default None — no fields required."""
        r = ViewerConfigUpdateRequest()
        assert r.custom is None

    def test_round_trip(self):
        r = ViewerConfigUpdateRequest(custom="x")
        assert ViewerConfigUpdateRequest(**r.model_dump()) == r
