# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every redis client the upgrade builds turns maintenance notifications off.

Read from source because ``upgrade.py`` cannot be imported bare.
"""

import ast

from tests.helpers import SRC_ROOT


def _redis_calls():
    tree = ast.parse((SRC_ROOT / "initdb" / "upgrade.py").read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == "Redis"
    ]


def test_the_upgrade_builds_redis_clients():
    assert _redis_calls()


def test_every_upgrade_redis_client_turns_the_probe_off():
    missing = [
        call.lineno
        for call in _redis_calls()
        if not any(k.arg == "maint_notifications_config" for k in call.keywords)
    ]
    assert missing == []
