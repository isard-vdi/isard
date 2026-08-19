"""Unit tests for the v207 main-domain certificate seed.

The decision of WHAT to seed lives in ``upgrade_helpers.py`` so it can be loaded
bare (``upgrade.py`` itself cannot: humanfriendly, rethinkdb, config). The
single ``update`` around it is trivial; the rules below are not.

This migration is what turns the move of the certificate configuration into the
database into a migration rather than a second source of truth beside
isardvdi.cfg. Every existing install already has a working main domain, and it
must appear in the new admin UI without anyone retyping it.

Three rules carry the weight:

* it must never clobber a configuration that is already there, because
  ``_system_upgrades()`` runs on every boot and a restore from backup can
  replay an older version number over a configured deployment;
* it seeds the domain even when there is no ACME account, leaving
  ``certificate_source`` unset. That is the designed inert state: the issuance
  path no-ops without it, so an install that never used ACME gets its domain
  shown in the UI and nothing else changes;
* the domain is stored as a LIST. The shape is the expensive part to change
  later, and seeding a bare string would mean migrating live data again.
"""

import os
import runpy
import types

import pytest


def _load_helpers():
    ns = runpy.run_path(
        os.path.join(os.path.dirname(__file__), "upgrade_helpers.py"),
        run_name="_certificates_seed_under_test",
    )
    return types.SimpleNamespace(**ns)


m = _load_helpers()


FULL_ENV = {
    "DOMAIN": "vdi.example.com",
    "ACME_EMAIL": "ops@example.com",
    "ACME_SERVER": "letsencrypt",
}


# --- the shape --------------------------------------------------------------


def test_seeds_the_domain_as_a_list():
    seed = m.v207_main_domain_certificate_seed(FULL_ENV)
    assert seed["names"] == ["vdi.example.com"]


def test_seeds_the_acme_account():
    seed = m.v207_main_domain_certificate_seed(FULL_ENV)
    assert seed["certificate_source"] == "acme"
    assert seed["email"] == "ops@example.com"
    assert seed["acme_server"] == "letsencrypt"


def test_never_seeds_a_legacy_singular_name():
    seed = m.v207_main_domain_certificate_seed(FULL_ENV)
    assert "name" not in seed


def test_acme_server_defaults_when_unset():
    env = {"DOMAIN": "vdi.example.com", "ACME_EMAIL": "ops@example.com"}
    assert m.v207_main_domain_certificate_seed(env)["acme_server"] == "letsencrypt"


def test_domain_is_normalised_like_the_api_would():
    env = dict(FULL_ENV, DOMAIN="  VDI.Example.COM  ")
    assert m.v207_main_domain_certificate_seed(env)["names"] == ["vdi.example.com"]


# --- no ACME account: seed the domain, stay inert ---------------------------


def test_without_an_acme_email_the_domain_is_still_seeded():
    seed = m.v207_main_domain_certificate_seed({"DOMAIN": "vdi.example.com"})
    assert seed["names"] == ["vdi.example.com"]


def test_without_an_acme_email_no_certificate_source_is_set():
    """Issuance no-ops without it, which is exactly what an install that never
    used ACME should get: its domain visible, and nothing else changed."""
    seed = m.v207_main_domain_certificate_seed({"DOMAIN": "vdi.example.com"})
    assert "certificate_source" not in seed
    assert "email" not in seed


# --- where the domain comes from --------------------------------------------


def test_falls_back_to_video_domain():
    env = {"VIDEO_DOMAIN": "video.example.com"}
    assert m.v207_main_domain_certificate_seed(env)["names"] == ["video.example.com"]


def test_domain_wins_over_video_domain():
    env = {"DOMAIN": "vdi.example.com", "VIDEO_DOMAIN": "video.example.com"}
    assert m.v207_main_domain_certificate_seed(env)["names"] == ["vdi.example.com"]


def test_nothing_to_seed_without_any_domain():
    assert m.v207_main_domain_certificate_seed({}) is None


@pytest.mark.parametrize("blank", ["", "   ", "null", "None", "NULL"])
def test_placeholder_values_count_as_absent(blank):
    """A variable declared in docker-compose but unset in isardvdi.cfg is
    rendered as ``null`` in the generated compose file. Seeding the four
    characters n-u-l-l as a domain name would be worse than seeding nothing."""
    assert m.v207_main_domain_certificate_seed({"DOMAIN": blank}) is None


@pytest.mark.parametrize("blank", ["", "   ", "null", "None"])
def test_placeholder_acme_email_counts_as_absent(blank):
    env = {"DOMAIN": "vdi.example.com", "ACME_EMAIL": blank}
    assert "certificate_source" not in m.v207_main_domain_certificate_seed(env)


# --- idempotence: never clobber ---------------------------------------------


def test_does_not_touch_an_existing_configuration():
    existing = {"names": ["already.example.com"], "certificate_source": "acme"}
    assert m.v207_main_domain_certificate_seed(FULL_ENV, existing) is None


def test_an_empty_existing_block_is_treated_as_absent():
    for empty in (None, {}):
        assert m.v207_main_domain_certificate_seed(FULL_ENV, empty) is not None


def test_a_partially_configured_block_is_left_alone():
    """Half a configuration is still somebody's configuration; overwriting it
    would undo a deliberate edit made through the admin UI."""
    existing = {"names": ["chosen.example.com"]}
    assert m.v207_main_domain_certificate_seed(FULL_ENV, existing) is None


def test_running_twice_produces_the_same_document():
    once = m.v207_main_domain_certificate_seed(FULL_ENV)
    twice = m.v207_main_domain_certificate_seed(FULL_ENV)
    assert once == twice
    # And a second pass over the result it just wrote is a no-op.
    assert m.v207_main_domain_certificate_seed(FULL_ENV, once) is None


def test_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("DOMAIN", "from-environ.example.com")
    monkeypatch.delenv("ACME_EMAIL", raising=False)
    monkeypatch.delenv("VIDEO_DOMAIN", raising=False)
    assert m.v207_main_domain_certificate_seed()["names"] == [
        "from-environ.example.com"
    ]
