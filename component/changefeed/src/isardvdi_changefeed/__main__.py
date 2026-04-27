#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Simó Albert i Beltran, Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import json
import logging as log
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from isardvdi_common.connections.redis_urls import changefeed_url
from pydantic import BaseModel, ConfigDict

from .table_changefeed import TableChangefeed


# The set of tables and their RethinkDB ``pluck`` projections lives in a
# sibling ``tables.json`` file so the AsyncAPI contract generator
# (``docker/codegen/gen_changefeed_asyncapi.py``) can consume the exact same
# source of truth at build time.
class _TableEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    pluck: list[Any] | None = None
    stream: bool = False
    stream_maxlen: int = 10000
    squash: float = 0.5


def _load_tables() -> list[dict]:
    path = Path(__file__).parent / "tables.json"
    raw = json.loads(path.read_text())
    entries = [_TableEntry.model_validate(e) for e in raw]
    return [e.model_dump(exclude_none=True) for e in entries]


changefeed_tables = _load_tables()


async def main():
    redis = aioredis.from_url(changefeed_url(), decode_responses=True)
    await redis.ping()
    log.info("Connected to Redis successfully.")

    await TableChangefeed(changefeed_tables, redis).run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down async changefeed listeners.")
