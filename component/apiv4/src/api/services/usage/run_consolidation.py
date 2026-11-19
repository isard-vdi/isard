# Usage consolidation, run in a process of its own
# SPDX-License-Identifier: AGPL-3.0-or-later
#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.

"""Usage consolidation child: started by path by ``isolated``, prints a JSON summary."""

import argparse
import importlib.util
import json
import os
import resource
import sys
import time

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 3

_SRC = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _bootstrap() -> None:
    """Import ``api.*`` without running ``api/__init__.py``, which builds the app."""
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != here]
    if _SRC not in sys.path:
        sys.path.insert(0, _SRC)
    if "api" in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        "api",
        os.path.join(_SRC, "api", "__init__.py"),
        submodule_search_locations=[os.path.join(_SRC, "api")],
    )
    # Real spec without exec: the log formatter names the service from its origin.
    sys.modules["api"] = importlib.util.module_from_spec(spec)


def _max_rss_mib() -> float:
    # ru_maxrss is in KiB on Linux.
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--item-type", default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--run-id", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    _bootstrap()

    import logging

    import api.dependencies.log_config  # noqa: F401  (JSON logging, as the API)

    log = logging.getLogger("apiv4")

    from api.services.admin.usage import AdminUsageService
    from api.services.usage.consolidate import ConsolidateConsumption
    from isardvdi_common.helpers.error_base import ErrorBase

    call = []
    if args.item_type is not None or args.days is not None:
        call = [args.item_type, 29 if args.days is None else args.days]

    summary = {
        "run_id": args.run_id,
        "item_type": args.item_type,
        "days": args.days,
        "pid": os.getpid(),
    }
    log.info("usage consolidation child started %s", json.dumps(summary))
    start = time.monotonic()
    code = EXIT_OK
    try:
        AdminUsageService.consolidate_consumptions(*call)
        summary["ok"] = True
    except ErrorBase as error:
        code = EXIT_REJECTED
        summary["ok"] = False
        summary["error"] = error.error.get("error", "bad_request")
        summary["description"] = error.error.get("description", str(error))
        summary["description_code"] = error.error.get("description_code")
    except Exception as exc:  # noqa: BLE001  (reported to the parent, not lost)
        code = EXIT_FAILED
        summary["ok"] = False
        summary["exception"] = type(exc).__name__
        summary["message"] = str(exc)
        log.exception("usage consolidation child failed")
    summary["elapsed_s"] = round(time.monotonic() - start, 2)
    summary["inserted"] = ConsolidateConsumption.inserted_total
    summary["failed_batches"] = ConsolidateConsumption.failed_batches
    summary["max_rss_mib"] = _max_rss_mib()
    log.info("usage consolidation child finished %s", json.dumps(summary))
    sys.stdout.write(json.dumps(summary) + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
