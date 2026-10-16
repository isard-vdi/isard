# SPDX-License-Identifier: AGPL-3.0-or-later

"""``REDIS_TASK_RESULT_TTL`` reaches every container that creates or cancels tasks."""

import re
from pathlib import Path

import pytest

_PARTS = Path(__file__).resolve().parents[3] / "docker-compose-parts"
_DECLARATION = re.compile(
    r"^\s*REDIS_TASK_RESULT_TTL:\s*\$\{REDIS_TASK_RESULT_TTL:-2592000\}\s*$", re.M
)


@pytest.mark.parametrize("part", ["apiv4.yml", "change-handler.yml", "engine.yml"])
def test_task_producers_receive_the_ttl_with_its_default(part):
    text = (_PARTS / part).read_text(encoding="utf-8")
    assert _DECLARATION.search(text), f"{part} must pass REDIS_TASK_RESULT_TTL"
