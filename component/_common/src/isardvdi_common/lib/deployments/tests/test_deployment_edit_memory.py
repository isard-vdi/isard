#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for the deployment-edit memory conversion."""

from isardvdi_common.lib.deployments import deployments as mod

CONVERT = mod.DeploymentsProcessed._convert_and_propagate_edited_memory


def test_memory_converted_to_kib_on_deployment_and_propagated_to_desktop_data():
    dep_hw = {"memory": 8.0, "vcpus": 4}
    desktop_data = {"hardware": {"memory": 8.0, "vcpus": 4}}
    CONVERT(dep_hw, desktop_data)
    assert dep_hw["memory"] == 8388608  # 8 GiB in KiB
    assert desktop_data["hardware"]["memory"] == 8388608  # domain rows get KiB too


def test_rename_without_hardware_does_not_keyerror():
    """A rename carries no ``hardware`` key; the conversion must not KeyError."""
    dep_hw = {"memory": 8.0}
    desktop_data = {"name": "renamed"}
    CONVERT(dep_hw, desktop_data)  # must not raise
    assert dep_hw["memory"] == 8388608
    assert "hardware" not in desktop_data


def test_hardware_edit_without_memory_key_is_left_untouched():
    dep_hw = {"memory": 8.0}
    desktop_data = {"hardware": {"vcpus": 8}}  # changed vcpus only, not memory
    CONVERT(dep_hw, desktop_data)
    assert dep_hw["memory"] == 8388608
    assert "memory" not in desktop_data["hardware"]


def test_sub_minimum_memory_is_rounded_up():
    """A sub-minimum value (here a corrupt 8-KiB row) is rounded up to the floor,
    not rejected — installs may legitimately hold sub-minimum values."""
    dep_hw = {"memory": 8 / 1048576}
    desktop_data = {"hardware": {"memory": 8 / 1048576}}
    CONVERT(dep_hw, desktop_data)
    assert dep_hw["memory"] == 25600  # 25 MiB floor
    assert desktop_data["hardware"]["memory"] == 25600
