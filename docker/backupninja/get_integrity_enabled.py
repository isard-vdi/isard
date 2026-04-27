#!/usr/bin/env python3
"""
Fetch the weekly borg integrity check toggle from the IsardVDI API.

Called live by each *-borg-integrity.sh script on Saturdays (just before
running `borg check`), so admins can flip the webapp setting without
restarting the backupninja container. Prints "true" or "false" to stdout,
or nothing on any error (logged to stderr); callers treat anything other
than "true" as off, matching the API's default-off policy.
"""

import sys


def main() -> int:
    try:
        from isardvdi_common.api_rest import ApiRest

        data = ApiRest("isard-api").get("/admin/backups/integrity") or {}
    except Exception as exc:  # noqa: BLE001 - helper must never crash the container
        sys.stderr.write(f"integrity toggle fetch failed: {exc}\n")
        return 0

    print("true" if data.get("integrity_enabled") else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
