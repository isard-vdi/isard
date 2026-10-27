# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the stored guest RDP state is read."""

import pytest
from isardvdi_common.helpers import rdp_security as mod


def test_a_guest_refusing_tls_reads_as_standard_rdp_security():
    rdp = {"state": "refused", "protocol": None, "reason": "tls_not_allowed", "at": 1}
    assert mod.rdp_effective(rdp) == {
        "state": "unverified",
        "protocol": "rdp",
        "reason": None,
        "at": 1,
    }


@pytest.mark.parametrize(
    "rdp",
    [
        None,
        {"state": "unverified", "protocol": "rdp", "reason": None},
        {"state": "ready", "protocol": "nla", "reason": None},
        {"state": "waiting", "protocol": None, "reason": "port_closed"},
        {"state": "refused", "protocol": None, "reason": "nla_required"},
    ],
)
def test_other_states_are_left_alone(rdp):
    assert mod.rdp_effective(rdp) == rdp
