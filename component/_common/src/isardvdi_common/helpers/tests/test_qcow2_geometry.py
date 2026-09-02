#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the installation-wide qcow2 geometry helper.

The geometry policy is resolved ONCE by the enqueuing process and carried in
the task payload; the worker applies it verbatim. This module pins the pure
helpers that both sides share: parsing, validation, the ``-o`` option string,
and the memoised ``policy()`` resolution from the environment.
"""

import isardvdi_common.helpers.qcow2_geometry as qg
import pytest


def _default():
    return {
        "cluster_size": "4k",
        "extended_l2": "off",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }


# --- parse_cluster_size ------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("4k", 4096),
        ("128k", 131072),
        ("16K", 16384),
        ("1M", 1024**2),
        ("65536", 65536),
    ],
)
def test_parse_cluster_size(value, expected):
    assert qg.parse_cluster_size(value) == expected


def test_parse_cluster_size_rejects_non_size():
    with pytest.raises(qg.Qcow2PolicyError):
        qg.parse_cluster_size("notasize")


# --- validate ----------------------------------------------------------------


def test_validate_accepts_and_returns_the_default_policy():
    geo = _default()
    assert qg.validate(geo) is geo


@pytest.mark.parametrize(
    "key", ["cluster_size", "extended_l2", "lazy_refcounts", "preallocation"]
)
def test_validate_rejects_a_missing_key(key):
    geo = _default()
    geo[key] = None
    with pytest.raises(qg.Qcow2PolicyError, match=key):
        qg.validate(geo)


@pytest.mark.parametrize(
    "key", ["cluster_size", "extended_l2", "lazy_refcounts", "preallocation"]
)
def test_validate_rejects_an_empty_key(key):
    geo = _default()
    geo[key] = ""
    with pytest.raises(qg.Qcow2PolicyError, match=key):
        qg.validate(geo)


def test_validate_rejects_a_bad_extended_l2():
    geo = _default()
    geo["extended_l2"] = "yes"
    with pytest.raises(qg.Qcow2PolicyError):
        qg.validate(geo)


def test_validate_rejects_a_bad_lazy_refcounts():
    geo = _default()
    geo["lazy_refcounts"] = "maybe"
    with pytest.raises(qg.Qcow2PolicyError):
        qg.validate(geo)


def test_validate_rejects_a_bad_preallocation():
    geo = _default()
    geo["preallocation"] = "sparse"
    with pytest.raises(qg.Qcow2PolicyError):
        qg.validate(geo)


def test_validate_rejects_extended_l2_with_too_small_cluster():
    geo = _default()
    geo["extended_l2"] = "on"
    geo["cluster_size"] = "4k"
    with pytest.raises(qg.Qcow2PolicyError, match="extended_l2"):
        qg.validate(geo)


def test_validate_accepts_extended_l2_with_16k_cluster():
    geo = _default()
    geo["extended_l2"] = "on"
    geo["cluster_size"] = "16k"
    assert qg.validate(geo) is geo


# --- from_env / policy -------------------------------------------------------


def test_from_env_reads_the_four_vars():
    env = {
        "QCOW2_CLUSTER_SIZE": "128k",
        "QCOW2_EXTENDED_L2": "on",
        "QCOW2_LAZY_REFCOUNTS": "on",
        "QCOW2_PREALLOCATION": "metadata",
    }
    assert qg.from_env(env) == {
        "cluster_size": "128k",
        "extended_l2": "on",
        "lazy_refcounts": "on",
        "preallocation": "metadata",
    }


def test_from_env_falls_back_to_defaults_when_absent():
    assert qg.from_env({}) == _default()


def test_from_env_falls_back_to_defaults_when_empty():
    env = {
        "QCOW2_CLUSTER_SIZE": "",
        "QCOW2_EXTENDED_L2": "",
        "QCOW2_LAZY_REFCOUNTS": "",
        "QCOW2_PREALLOCATION": "",
    }
    assert qg.from_env(env) == _default()


def test_from_env_validates():
    env = {"QCOW2_EXTENDED_L2": "on", "QCOW2_CLUSTER_SIZE": "4k"}
    with pytest.raises(qg.Qcow2PolicyError):
        qg.from_env(env)


def test_policy_is_memoised(monkeypatch):
    monkeypatch.setattr(qg, "_cached", None)
    monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "128k")
    monkeypatch.setenv("QCOW2_EXTENDED_L2", "off")
    monkeypatch.setenv("QCOW2_LAZY_REFCOUNTS", "off")
    monkeypatch.setenv("QCOW2_PREALLOCATION", "off")
    first = qg.policy()
    assert first["cluster_size"] == "128k"
    # Changing the environment does not change an already-resolved policy.
    monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "4k")
    assert qg.policy() is first


# --- create_options ----------------------------------------------------------


def test_create_options_parentless_appends_preallocation():
    geo = _default()
    assert qg.create_options(geo, has_backing_file=False) == (
        "cluster_size=4k,extended_l2=off,lazy_refcounts=off,preallocation=off"
    )


def test_create_options_with_backing_and_extended_off_omits_preallocation():
    geo = _default()
    assert qg.create_options(geo, has_backing_file=True) == (
        "cluster_size=4k,extended_l2=off,lazy_refcounts=off"
    )


def test_create_options_with_backing_and_extended_on_appends_preallocation():
    geo = {
        "cluster_size": "16k",
        "extended_l2": "on",
        "lazy_refcounts": "on",
        "preallocation": "metadata",
    }
    assert qg.create_options(geo, has_backing_file=True) == (
        "cluster_size=16k,extended_l2=on,lazy_refcounts=on,preallocation=metadata"
    )


def test_create_options_validates():
    geo = _default()
    geo["preallocation"] = "bogus"
    with pytest.raises(qg.Qcow2PolicyError):
        qg.create_options(geo, has_backing_file=False)
