# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for api/schemas/domains/desktop_direct_viewer.py.

The DesktopViewerScheduled.shutdown field must accept every shape the
backing service returns. Previously declaring it as bare ``bool`` made
Pydantic reject the ISO datetime string the service emits when a desktop
has a scheduled shutdown, which the direct-viewer route then swallowed
into a 404 — breaking every /vw/<token> flow on affected desktops.
"""

from datetime import datetime, timezone

import pytest
from api.schemas.domains.desktop_direct_viewer import DesktopViewerScheduled
from pydantic import ValidationError


class TestDesktopViewerScheduledShutdown:
    def test_accepts_iso_datetime_string(self):
        """The engine writes scheduled.shutdown as an ISO8601 timestamp with tz."""
        m = DesktopViewerScheduled(shutdown="2026-04-20T21:44+0000")
        assert isinstance(m.shutdown, datetime)

    def test_accepts_datetime_object(self):
        dt = datetime(2026, 4, 20, 21, 44, tzinfo=timezone.utc)
        m = DesktopViewerScheduled(shutdown=dt)
        assert m.shutdown == dt

    def test_accepts_literal_false(self):
        """When no shutdown is scheduled the service returns False, not None."""
        m = DesktopViewerScheduled(shutdown=False)
        assert m.shutdown is False

    def test_accepts_none(self):
        m = DesktopViewerScheduled(shutdown=None)
        assert m.shutdown is None

    def test_default_is_false(self):
        m = DesktopViewerScheduled()
        assert m.shutdown is False

    def test_rejects_truthy_bool(self):
        """True is not a valid shutdown value; only datetime / False / None."""
        with pytest.raises(ValidationError):
            DesktopViewerScheduled(shutdown=True)

    def test_rejects_arbitrary_string(self):
        with pytest.raises(ValidationError):
            DesktopViewerScheduled(shutdown="not-a-date")
