# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for registering an account against an acme-dns server.

acme-dns exists so that a DNS-01 challenge never needs credentials for the
customer's real zone. It hands out a throwaway subdomain and a username and
password that can only write the TXT record under it; the customer delegates
_acme-challenge.<their domain> to that subdomain with one CNAME, once, and from
then on renewal is unattended.

Everything the operator has to do afterwards depends on this call returning
exactly what the server said, so the parts worth pinning are about not losing
or inventing any of it:

* the response must be complete before it is stored. A registration missing
  the subdomain looks like it worked, produces a CNAME instruction the operator
  dutifully asks their customer to create, and only fails much later at
  issuance -- by which time the person who could fix the DNS has moved on.

* the password must not surface in an error. This module is the one place that
  ever sees it in a response body, and requests puts the URL, not the body, in
  its exception text -- but the temptation to include the response on failure
  is exactly how it would end up in a log.

What is deliberately NOT here is any protection against registering twice.
acme-dns has no update and no delete, so a second registration strands the
first account and invalidates the CNAME the customer already created. Nothing
in this function can tell the two cases apart -- it is handed a URL and asked
to register -- so refusing to overwrite credentials in use belongs to the
caller that can see what is stored, and is tested there.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def acmedns():
    return importlib.import_module("isardvdi_common.helpers.acmedns")


@pytest.fixture
def response():
    """A well-formed acme-dns /register response."""
    return {
        "username": "eabcdb41-d89f-4580-826f-3e62e9755ef2",
        "password": "htB9mR9DYgcu9bX_afHF62erXaH2TS7bg9KW3F7Z",
        "fulldomain": "d420c923-bbd7-4056-ab64-c3ca54c9b3cf.auth.example.com",
        "subdomain": "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
        "allowfrom": [],
    }


@pytest.fixture
def post(acmedns, response):
    """Stub requests.post, answering with the fixture body by default."""
    with patch.object(acmedns.requests, "post") as mock_post:
        reply = MagicMock(name="response")
        reply.json.return_value = response
        reply.raise_for_status.return_value = None
        mock_post.return_value = reply
        yield mock_post


# ── The call itself ──────────────────────────────────────────────────────


class TestRequest:
    def test_it_posts_to_the_register_endpoint(self, acmedns, post):
        acmedns.register("https://auth.example.com")
        assert post.call_args.args[0] == "https://auth.example.com/register"

    def test_a_trailing_slash_does_not_double_up(self, acmedns, post):
        acmedns.register("https://auth.example.com/")
        assert post.call_args.args[0] == "https://auth.example.com/register"

    def test_it_does_not_wait_forever(self, acmedns, post):
        """This runs on a request thread the operator is watching."""
        acmedns.register("https://auth.example.com")
        assert post.call_args.kwargs["timeout"]

    def test_it_registers_without_an_allowfrom(self, acmedns, post):
        """Deliberate, and the reason is written in the module: our acme-dns
        runs with use_header and the proxy in front of it does not add the
        header, so an account restricted by IP answers 401 even from the right
        one. Sending an allowfrom would produce credentials that never work."""
        acmedns.register("https://auth.example.com")
        body = post.call_args.kwargs.get("json") or {}
        assert "allowfrom" not in body

    def test_a_missing_base_url_is_refused_before_any_request(self, acmedns, post):
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.register("")
        post.assert_not_called()


# ── What comes back ──────────────────────────────────────────────────────


class TestResponse:
    def test_it_returns_the_four_credentials(self, acmedns, post, response):
        creds = acmedns.register("https://auth.example.com")
        assert creds == {
            "base_url": "https://auth.example.com",
            "username": response["username"],
            "password": response["password"],
            "subdomain": response["subdomain"],
            "fulldomain": response["fulldomain"],
        }

    def test_the_base_url_it_was_given_travels_with_them(self, acmedns, post):
        """The credentials are worthless without knowing which server issued
        them, and storing them apart is how they get separated."""
        creds = acmedns.register("https://auth.example.com/")
        assert creds["base_url"] == "https://auth.example.com"

    @pytest.mark.parametrize(
        "missing", ["username", "password", "subdomain", "fulldomain"]
    )
    def test_an_incomplete_response_is_refused(self, acmedns, post, response, missing):
        """Storing half a registration produces a CNAME instruction the
        operator passes on to their customer, and the failure only shows up at
        issuance, long after anyone is still looking."""
        del response[missing]
        with pytest.raises(acmedns.AcmeDnsError) as excinfo:
            acmedns.register("https://auth.example.com")
        assert missing in str(excinfo.value)

    def test_an_empty_field_counts_as_missing(self, acmedns, post, response):
        response["subdomain"] = ""
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.register("https://auth.example.com")

    def test_a_body_that_is_not_json_is_reported_as_such(self, acmedns, post):
        post.return_value.json.side_effect = ValueError("no json here")
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.register("https://auth.example.com")


# ── Failures ─────────────────────────────────────────────────────────────


class TestFailure:
    def test_an_http_error_becomes_an_acme_dns_error(self, acmedns, post):
        post.return_value.raise_for_status.side_effect = Exception("500 boom")
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.register("https://auth.example.com")

    def test_an_unreachable_server_becomes_an_acme_dns_error(self, acmedns, post):
        post.side_effect = OSError("connection refused")
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.register("https://auth.example.com")

    def test_the_message_names_the_server(self, acmedns, post):
        """Typing the wrong URL is the likeliest way for this to fail, so the
        message has to show what was actually contacted."""
        post.side_effect = OSError("connection refused")
        with pytest.raises(acmedns.AcmeDnsError) as excinfo:
            acmedns.register("https://typo.example.com")
        assert "typo.example.com" in str(excinfo.value)

    def test_a_failure_never_carries_the_response_body(self, acmedns, post, response):
        """The body of a successful registration holds the password. Echoing a
        response into an error message is how it reaches a log."""
        post.return_value.raise_for_status.side_effect = Exception(
            f"500 Server Error: {response}"
        )
        with pytest.raises(acmedns.AcmeDnsError) as excinfo:
            acmedns.register("https://auth.example.com")
        assert response["password"] not in str(excinfo.value)
