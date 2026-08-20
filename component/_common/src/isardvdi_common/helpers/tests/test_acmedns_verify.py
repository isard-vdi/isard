# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for checking that the operator's CNAME delegation is in place.

Registering an acme-dns account is the easy half. The half that involves
another organisation is the CNAME: somebody at the customer has to point
_acme-challenge.<domain> at the fulldomain acme-dns handed out, and until they
have, issuance fails. This check exists so the operator finds that out while
they are still looking at the screen, rather than from a certificate that never
appears.

The design constraint that shapes all of it: the answer that matters is the one
a certificate authority will get, from the public internet, and we are not
sitting there. So the check reports what it saw and from where, and never
pretends a negative answer is authoritative.

Three properties carry the weight.

It must not pin a public resolver. The reference implementation hardcoded
8.8.8.8 with configure=False, so /etc/resolv.conf was deliberately ignored. On
any deployment with filtered egress -- which is a normal way to run this
product -- that reports "not visible" forever, for every domain, no matter what
the operator does. The failure looks identical to a CNAME that was never
created, so the operator has no way to tell they are chasing nothing.

A record pointing at the WRONG target must not read the same as no record at
all. Both mean "cannot issue yet", but one is fixed by waiting and the other
never is: it usually means the delegation points at an earlier registration
that has since been replaced. Telling the operator to wait for propagation
there is advice that can never come true.

Not-found must not raise. This gets polled while the operator waits for DNS to
propagate, and an exception per attempt is noise, not information.
"""

import importlib
from unittest.mock import MagicMock, patch

import dns.resolver
import pytest

RECORD = "_acme-challenge.vdi.example.com"
FULLDOMAIN = "d420c923-bbd7-4056-ab64-c3ca54c9b3cf.auth.example.com"


@pytest.fixture
def acmedns():
    return importlib.import_module("isardvdi_common.helpers.acmedns")


class _FakeResolver:
    """Stands in for dns.resolver.Resolver, one instance per lookup.

    Answers are keyed by the nameserver list the caller configured, so a test
    can make the system resolver and the public fallback disagree -- which is
    the split-horizon case the fallback exists for.
    """

    instances = []

    def __init__(self, *args, **kwargs):
        self.nameservers = ["203.0.113.53"]  # what /etc/resolv.conf yielded
        self.timeout = None
        self.lifetime = None
        _FakeResolver.instances.append(self)

    def resolve(self, name, kind):
        key = ",".join(self.nameservers)
        answer = _FakeResolver.answers.get(key, _FakeResolver.answers.get("*"))
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise dns.resolver.NXDOMAIN()
        record = MagicMock()
        record.to_text.return_value = answer
        return [record]


@pytest.fixture
def resolver(acmedns, monkeypatch):
    """Install the fake resolver and expose its answer table."""
    _FakeResolver.instances = []
    _FakeResolver.answers = {"*": FULLDOMAIN + "."}
    monkeypatch.setattr(acmedns.dns.resolver, "Resolver", _FakeResolver)
    monkeypatch.delenv(acmedns._NAMESERVERS_ENV, raising=False)
    return _FakeResolver


# ── Which resolver gets asked ────────────────────────────────────────────


class TestResolverChoice:
    def test_it_uses_the_system_resolver_first(self, acmedns, resolver):
        """The one thing the reference got wrong. Reading /etc/resolv.conf is
        what makes this work on a deployment that cannot reach the public
        internet directly, which is a normal way to run this product."""
        acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert resolver.instances[0].nameservers == ["203.0.113.53"]

    def test_the_system_resolver_is_not_bypassed_by_construction(
        self, acmedns, resolver
    ):
        """dns.resolver.Resolver(configure=False) is what pinned the reference
        to 8.8.8.8: it skips /etc/resolv.conf entirely."""
        acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        first = resolver.instances[0]
        assert first.nameservers, "the system resolver's nameservers were discarded"

    def test_the_nameservers_can_be_configured(self, acmedns, resolver, monkeypatch):
        monkeypatch.setenv(acmedns._NAMESERVERS_ENV, "192.0.2.53, 192.0.2.54")
        resolver.answers = {"192.0.2.53,192.0.2.54": FULLDOMAIN + "."}
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is True
        assert resolver.instances[0].nameservers == ["192.0.2.53", "192.0.2.54"]

    def test_a_configured_resolver_is_used_alone(self, acmedns, resolver, monkeypatch):
        """An operator who names a resolver means that one. Falling back to a
        public one behind their back would answer a question they did not ask,
        and on a filtered network it would just add a timeout to every check."""
        monkeypatch.setenv(acmedns._NAMESERVERS_ENV, "192.0.2.53")
        resolver.answers = {"*": None}
        acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert len(resolver.instances) == 1

    def test_it_asks_the_challenge_name_not_the_domain(self, acmedns, resolver):
        with patch.object(
            _FakeResolver, "resolve", side_effect=dns.resolver.NXDOMAIN()
        ) as resolve:
            acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert resolve.call_args.args[0] == RECORD
        assert resolve.call_args.args[1] == "CNAME"

    def test_the_lookup_is_bounded(self, acmedns, resolver):
        """Polled from a request thread while the operator waits."""
        acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert resolver.instances[0].timeout
        assert resolver.instances[0].lifetime


# ── The falling back ─────────────────────────────────────────────────────


class TestFallback:
    def test_a_public_resolver_is_tried_when_the_system_one_cannot_see_it(
        self, acmedns, resolver
    ):
        """Split horizon: an internal resolver serving a private view of the
        zone will not have the delegation the certificate authority will see."""
        resolver.answers = {
            "203.0.113.53": None,
            ",".join(acmedns._PUBLIC_FALLBACK): FULLDOMAIN + ".",
        }
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is True
        assert len(resolver.instances) == 2

    def test_an_unreachable_fallback_does_not_lose_the_first_answer(
        self, acmedns, resolver
    ):
        """Filtered egress: the fallback cannot be reached at all. The check
        still has to report what the system resolver said instead of failing."""
        resolver.answers = {
            "203.0.113.53": None,
            ",".join(acmedns._PUBLIC_FALLBACK): dns.resolver.LifetimeTimeout(),
        }
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is False
        assert result["message"]

    def test_a_verified_answer_stops_the_search(self, acmedns, resolver):
        acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert len(resolver.instances) == 1

    def test_a_negative_names_the_resolver_that_made_the_observation(
        self, acmedns, resolver
    ):
        """Not merely the last one tried. Attributing the system resolver's
        answer to the public ones destroys the only thing the two-resolver
        design buys: an operator told the public resolvers see a wrong target
        goes to change public DNS, when what actually happened is that their
        own resolver holds a private view and the public ones never answered."""
        resolver.answers = {
            "203.0.113.53": "somewhere-else.example.com.",
            ",".join(acmedns._PUBLIC_FALLBACK): dns.resolver.LifetimeTimeout(),
        }
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)

        assert result["observed"] == "somewhere-else.example.com"
        assert result["resolver"] == "system"

    def test_a_negative_with_no_answer_at_all_names_what_was_tried(
        self, acmedns, resolver
    ):
        """Nothing observed it, so the honest thing is to say where it was
        looked for."""
        resolver.answers = {"*": None}
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)

        assert result["observed"] is None
        assert acmedns._PUBLIC_FALLBACK[0] in result["resolver"]

    def test_it_says_which_resolver_answered(self, acmedns, resolver):
        """So the operator can tell "my resolver cannot see it" from "the
        record is not there", which need different things done about them."""
        resolver.answers = {
            "203.0.113.53": None,
            ",".join(acmedns._PUBLIC_FALLBACK): FULLDOMAIN + ".",
        }
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert acmedns._PUBLIC_FALLBACK[0] in result["resolver"]


# ── Reading the answer ───────────────────────────────────────────────────


class TestAnswer:
    def test_a_matching_record_verifies(self, acmedns, resolver):
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is True
        assert result["observed"] == FULLDOMAIN

    def test_the_trailing_dot_does_not_matter(self, acmedns, resolver):
        resolver.answers = {"*": FULLDOMAIN}
        assert acmedns.verify_cname("vdi.example.com", FULLDOMAIN + ".")["verified"]

    def test_case_does_not_matter(self, acmedns, resolver):
        """DNS names are case-insensitive and some resolvers randomise it."""
        resolver.answers = {"*": FULLDOMAIN.upper() + "."}
        assert acmedns.verify_cname("vdi.example.com", FULLDOMAIN)["verified"]

    def test_a_record_pointing_somewhere_else_is_not_verified(self, acmedns, resolver):
        resolver.answers = {"*": "someone-elses-subdomain.auth.example.com."}
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is False

    def test_a_wrong_target_is_reported_as_a_wrong_target(self, acmedns, resolver):
        """Not the same finding as a missing record. Waiting fixes a missing
        one; waiting never fixes a delegation aimed at a stale registration,
        so the operator has to be told what it actually points at."""
        resolver.answers = {"*": "stale.auth.example.com."}
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["observed"] == "stale.auth.example.com"
        assert "stale.auth.example.com" in result["message"]
        assert FULLDOMAIN in result["message"]

    def test_a_missing_record_reports_what_to_create(self, acmedns, resolver):
        resolver.answers = {"*": None}
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is False
        assert result["observed"] is None
        assert RECORD in result["message"]
        assert FULLDOMAIN in result["message"]

    def test_the_expected_target_is_always_reported(self, acmedns, resolver):
        resolver.answers = {"*": None}
        assert acmedns.verify_cname("vdi.example.com", FULLDOMAIN)["expected"] == (
            FULLDOMAIN
        )


# ── Not raising ──────────────────────────────────────────────────────────


class TestDoesNotRaise:
    @pytest.mark.parametrize(
        "failure",
        [
            dns.resolver.NXDOMAIN(),
            dns.resolver.NoAnswer(),
            dns.resolver.LifetimeTimeout(),
            dns.resolver.NoNameservers(),
        ],
    )
    def test_a_lookup_failure_is_an_unverified_result(self, acmedns, resolver, failure):
        """This is polled while the operator waits for propagation. An
        exception per attempt is noise rather than information."""
        resolver.answers = {"*": failure}
        result = acmedns.verify_cname("vdi.example.com", FULLDOMAIN)
        assert result["verified"] is False

    def test_a_missing_fulldomain_is_refused_rather_than_guessed(
        self, acmedns, resolver
    ):
        """Without it there is nothing to compare against, and a check that
        cannot fail would report every domain as verified."""
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.verify_cname("vdi.example.com", "")

    def test_a_missing_domain_is_refused(self, acmedns, resolver):
        with pytest.raises(acmedns.AcmeDnsError):
            acmedns.verify_cname("", FULLDOMAIN)
