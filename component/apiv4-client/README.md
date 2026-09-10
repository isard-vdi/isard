# isardvdi-apiv4-client

Python client for the IsardVDI apiv4 HTTP API.

The package bundles two modules:

- **`isardvdi_apiv4_client/`** — generated from `pkg/oas/apiv4/apiv4.json`
  by `openapi-python-client` during `bash build.sh`. Do not edit: every
  build recreates it. Gitignored.

- **`isardvdi_apiv4_client_auth/`** — hand-written helpers: service JWT
  minting, base-URL discovery, and typed error wrapping. Checked in.

## Regenerating

```bash
# From repo root, with USAGE=build in isardvdi.cfg:
bash build.sh
```

## Using from a service

```python
from isardvdi_apiv4_client_auth import build_client, raise_for_status
from isardvdi_apiv4_client.api.admin_users import admin_user_list

with build_client("isard-scheduler") as client:
    resp = admin_user_list.sync_detailed(client=client)
    raise_for_status(resp)
    users = resp.parsed
```

`build_client(service)` accepts:

- `service` — `"isard-scheduler"`, `"isard-notifier"`, `"isard-hypervisor"`,
  `"isard-vpn"`, `"isard-webapp"`, `"isard-core-worker"`, `"isard-engine"`,
  `"isard-backupninja"`, `"isard-storage"`.
- `role` (optional) — `"admin"` (default) or `"hypervisor"`.
- `user_jwt` (optional) — passthrough JWT from a user request (webapp).
