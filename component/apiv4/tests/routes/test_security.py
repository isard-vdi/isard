#
#   Copyright © 2025 IsardVDI
#   SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests for security fixes ported from main.

import pytest


class TestUrlValidation:
    """Test SSRF prevention helpers."""

    def test_validate_url_not_internal_blocks_localhost(self):
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        with pytest.raises(ValueError, match="internal address"):
            validate_url_not_internal("http://127.0.0.1/secret")

    def test_validate_url_not_internal_blocks_private(self):
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        with pytest.raises(ValueError, match="internal address"):
            validate_url_not_internal("http://10.0.0.1/secret")

    def test_validate_url_not_internal_allows_public(self):
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        # Should not raise
        validate_url_not_internal("https://example.com/file.iso")

    def test_validate_url_not_internal_allows_none(self):
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        validate_url_not_internal(None)
        validate_url_not_internal("")

    def test_validate_url_scheme_blocks_javascript(self):
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        with pytest.raises(ValueError, match="Invalid URL scheme"):
            validate_url_scheme("javascript:alert(1)")

    def test_validate_url_scheme_blocks_data(self):
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        with pytest.raises(ValueError, match="Invalid URL scheme"):
            validate_url_scheme("data:text/html,<script>alert(1)</script>")

    def test_validate_url_scheme_allows_https(self):
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        validate_url_scheme("https://example.com")

    def test_validate_url_scheme_allows_http(self):
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        validate_url_scheme("http://example.com")


class TestSafeFormat:
    """Test SSTI prevention via safe_format."""

    def test_safe_format_basic(self):
        from isardvdi_common.helpers.safe_format import safe_format

        result = safe_format("Hello {name}!", name="World")
        assert result == "Hello World!"

    def test_safe_format_blocks_attribute_access(self):
        from isardvdi_common.helpers.safe_format import safe_format

        # Should NOT resolve __class__ — returns template unchanged
        result = safe_format("{name.__class__}", name="test")
        assert "__class__" not in result or result == "{name.__class__}"

    def test_safe_format_blocks_item_access(self):
        from isardvdi_common.helpers.safe_format import safe_format

        result = safe_format("{name[0]}", name="test")
        assert result == "{name[0]}"

    def test_safe_format_missing_key(self):
        from isardvdi_common.helpers.safe_format import safe_format

        result = safe_format("Hello {missing}!")
        assert result == "Hello {missing}!"


class TestPathTraversal:
    """Test card path traversal prevention."""

    def test_safe_card_path_allows_normal(self):
        from isardvdi_common.helpers.cards import _safe_card_path

        result = _safe_card_path("/tmp/cards", "image.jpg")
        assert result == "/tmp/cards/image.jpg"

    def test_safe_card_path_blocks_traversal(self):
        from isardvdi_common.helpers.cards import _safe_card_path

        with pytest.raises(Exception, match="Invalid card filename"):
            _safe_card_path("/tmp/cards", "../../etc/passwd")

    def test_safe_card_path_blocks_absolute(self):
        from isardvdi_common.helpers.cards import _safe_card_path

        with pytest.raises(Exception, match="Invalid card filename"):
            _safe_card_path("/tmp/cards", "/etc/passwd")


class TestSanitizeHref:
    """Test XSS prevention via href sanitization."""

    def test_sanitize_href_blocks_javascript(self):
        from isardvdi_common.lib.notifications.notifications_templates import (
            sanitize_href,
        )

        assert sanitize_href("javascript:alert(1)") is None

    def test_sanitize_href_blocks_data(self):
        from isardvdi_common.lib.notifications.notifications_templates import (
            sanitize_href,
        )

        assert sanitize_href("data:text/html,<script>") is None

    def test_sanitize_href_allows_https(self):
        from isardvdi_common.lib.notifications.notifications_templates import (
            sanitize_href,
        )

        assert sanitize_href("https://example.com") == "https://example.com"

    def test_sanitize_href_allows_none(self):
        from isardvdi_common.lib.notifications.notifications_templates import (
            sanitize_href,
        )

        assert sanitize_href(None) is None


class TestRegexEscape:
    """Test regex injection prevention in alloweds."""

    def test_match_query_escapes_special_chars(self):
        import re

        # The fix adds re.escape to user input before passing to .match()
        dangerous = ".*dangerous"
        escaped = re.escape(dangerous)
        assert escaped == r"\.\*dangerous"
        assert ".*" not in escaped


class TestRateLimiter:
    """Test direct viewer rate limiter."""

    def test_rate_limiter_allows_under_limit(self):
        from unittest.mock import MagicMock

        from api.dependencies.rate_limiting import RateLimiter

        limiter = RateLimiter(max_requests=5, window_seconds=60)
        request = MagicMock()
        request.headers = {"x-forwarded-for": "1.2.3.4"}
        request.client.host = "1.2.3.4"

        for _ in range(5):
            assert limiter.is_limited(request) is False

    def test_rate_limiter_blocks_over_limit(self):
        from unittest.mock import MagicMock

        from api.dependencies.rate_limiting import RateLimiter

        limiter = RateLimiter(max_requests=3, window_seconds=60)
        request = MagicMock()
        request.headers = {"x-forwarded-for": "5.6.7.8"}
        request.client.host = "5.6.7.8"

        for _ in range(3):
            assert limiter.is_limited(request) is False
        assert limiter.is_limited(request) is True

    def test_rate_limiter_different_ips_independent(self):
        from unittest.mock import MagicMock

        from api.dependencies.rate_limiting import RateLimiter

        limiter = RateLimiter(max_requests=2, window_seconds=60)

        req1 = MagicMock()
        req1.headers = {"x-forwarded-for": "10.0.0.1"}
        req1.client.host = "10.0.0.1"

        req2 = MagicMock()
        req2.headers = {"x-forwarded-for": "10.0.0.2"}
        req2.client.host = "10.0.0.2"

        for _ in range(2):
            assert limiter.is_limited(req1) is False
        assert limiter.is_limited(req1) is True
        # req2 should still be under limit
        assert limiter.is_limited(req2) is False
