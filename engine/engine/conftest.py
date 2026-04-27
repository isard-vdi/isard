"""Test bootstrap for engine changefeed consumer tests.

Importing the production modules pulls in `engine.config`, `engine.services.db`,
RethinkDB, Redis, etc. — which try to connect at import time and hang. We stub
the heavy modules in `sys.modules` *before* the test files import their targets.

We deliberately do NOT stub anything under `changefeed_models.*` — the tests
need the real Pydantic models for the change envelopes.
"""

import os
import sys
from unittest.mock import MagicMock

# Production modules evaluate `os.environ["DOMAIN"]` as a default argument at
# import time. Populate a placeholder so import doesn't KeyError.
os.environ.setdefault("DOMAIN", "test.example")

_STUBBED_MODULES = [
    "engine.config",
    "engine.services.db",
    "engine.services.db.db",
    "engine.services.db.domains",
    "engine.services.db.downloads",
    "engine.services.db.hypervisors",
    "engine.services.db.storage_pool",
    "engine.services.lib.functions",
    "engine.services.lib.qcow",
    "engine.services.lib.storage",
    "engine.services.log",
    "engine.services.threads.threads",
    "engine.models.pool_hypervisors",
    "changefeed_subscribers",
    "changefeed_subscribers.engine",
    "changefeed_subscribers.hypervisors",
    "isardvdi_common.redis_stream",
    "isardvdi_common.helpers.default_storage_pool",
    "rethinkdb",
    "humanfriendly",
]

for _mod in _STUBBED_MODULES:
    sys.modules.setdefault(_mod, MagicMock())

# `engine.services.log.logs` is accessed as `logs.main`, `logs.downloads`, etc.
# A bare MagicMock works because attribute access returns a child MagicMock,
# and calls like `logs.main.info(...)` are no-ops.
