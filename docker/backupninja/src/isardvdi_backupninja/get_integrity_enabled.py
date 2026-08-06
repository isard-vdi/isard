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
        from isardvdi_apiv4_client.api.role_admin import admin_backup_integrity_get
        from isardvdi_apiv4_client_auth import build_client, raise_for_status

        with build_client("isard-backupninja") as client:
            resp = admin_backup_integrity_get.sync_detailed(client=client)
            raise_for_status(resp)
        body = getattr(resp, "parsed", None) or {}
        enabled = (
            body.get("integrity_enabled")
            if isinstance(body, dict)
            else getattr(body, "integrity_enabled", None)
        )
    except Exception as exc:  # noqa: BLE001 - helper must never crash the container
        sys.stderr.write(f"integrity toggle fetch failed: {exc}\n")
        return 0

    print("true" if enabled else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
