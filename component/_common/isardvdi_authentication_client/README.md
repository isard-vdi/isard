# isardvdi-authentication-client

Python client for the IsardVDI `isard-authentication` HTTP API.

The package bundles two modules:

- **`isardvdi_authentication_client/`** — generated from
  `pkg/oas/authentication/authentication.json` by `openapi-python-client`
  during `bash build.sh`. Do not edit: every build recreates it.
  Gitignored.

- **`isardvdi_authentication_client_auth/`** — hand-written helpers:
  service JWT minting, base-URL discovery, and typed error wrapping.
  Checked in.

## Regenerating

```bash
# From repo root, with USAGE=build in isardvdi.cfg:
bash build.sh
```

## Using from a service

```python
from isardvdi_authentication_client_auth import build_client, raise_for_status
from isardvdi_authentication_client.api.default import migrate_user
from isardvdi_authentication_client.models import MigrateUserRequest

with build_client("isard-apiv4") as client:
    resp = migrate_user.sync_detailed(
        client=client,
        body=MigrateUserRequest(user_id=user_id),
    )
    raise_for_status(resp)
    token = resp.parsed.token
```

`build_client(service)` accepts:

- `service` — calling service's container name (stamped in the JWT
  `data.user_id` for audit traceability).
- `role` (optional) — `"admin"` (default) or `"hypervisor"`.
- `user_jwt` (optional) — passthrough JWT from a user request.
