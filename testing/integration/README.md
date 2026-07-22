# Real-stack integration tests

Exercises the IsardVDI VDI lifecycle end-to-end against a running stack:
download a domain from `registry.isardvdi.com` (e.g. TetrOS), add a
media from a URL (e.g. a tiny ISO from archive.org), create desktops
from both sources, start/stop them, create templates, derive new
desktops, and clean up — all through the public REST + SocketIO
surface.

These tests are tagged `@pytest.mark.real` and are skipped by the
default `pytest` invocation. They must run inside a container on the
docker-compose network so the test process can reach
`isard-apiv4:5000`, `isard-authentication:1313`, and
`isard-socketio:5000` by service name.

## Quick start — local devel stack

```
# Bring up the stack (unless already Up)
docker compose up -d

# Seed the admin_e2e_* users so the test has an admin account
python3 testing/db/populate_test_db.py

# Run the suite (inside a sidecar container on the isardvdi_default network)
docker compose -f docker-compose.yml -f docker-compose.integration.yml \
    run --rm integration-test-real
```

## Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `APIV4_URL` | `http://isard-apiv4:5000` | apiv4 FastAPI service |
| `AUTH_URL` | `http://isard-authentication:1313` | authentication service |
| `SOCKETIO_URL` | `http://isard-socketio:5000` | socketio server |
| `E2E_ADMIN_USER` | `admin_e2e_01` | seeded admin |
| `E2E_ADMIN_PWD` | `IsardTest1!` | seeded admin password |
| `E2E_ADMIN_CATEGORY` | `default` | login category |
| `E2E_NAMESPACE_PREFIX` | `e2e_real_<worker>_<ts>_` | object name prefix used for cleanup |
| `E2E_SKIP_STARTUP_CLEANUP` | — | set `1` to skip wiping prior `e2e_real_*` rows |
| `E2E_MEDIA_URL` | `https://archive.org/download/tiny-iso-test/TinyIsoTest.iso` | ISO used for media-from-URL flow |
| `E2E_REGISTRY_IMAGE` | `TetrOS` | registry image for download flow |
| `E2E_REGISTRY_CODE` | — | IsardVDI registration code; skips the registry test if absent |

## Cleanup

Every object created by the suite is named with the session prefix
`e2e_real_<worker>_<unix_ts>_<label>`. A session-scoped autouse
fixture:

- **Before the first test**: deletes any leftover `e2e_real_*` rows
  from a prior crashed run.
- **After the last test**: deletes everything under this session's
  prefix. Failures are logged, never raised — they do not mask real
  test failures.

Nuking the DB is not supported — this suite is additive.

You can also run the cleanup manually after an aborted run:

```
docker compose -f docker-compose.yml -f docker-compose.integration.yml \
    run --rm integration-test-real \
    python -m testing.integration.helpers.cleanup --prefix e2e_real_
```

## Layout

```
testing/integration/
  conftest.py                  # session fixtures: admin_client, ws, test_namespace, cleanup
  helpers/
    client.py                  # IsardClient (REST + poll_*_status)
    sockets.py                 # SocketIOListener (/administrators + /userspace)
    waits.py                   # generic polling helpers
    cleanup.py                 # delete-by-prefix + CLI entrypoint
  pytest.ini                   # registers the `real` marker, enables live logs
  requirements.txt             # pytest + requests + python-socketio
  test_registry_download_lifecycle.py
  test_media_from_url_lifecycle.py
  test_websocket_progress.py
```

## Why not Playwright?

All three regressions this suite reproduces are backend bugs (Pydantic
validation, KeyError from a schema migration, SocketIO room routing).
Driving the UI would add noise without adding coverage. A Vue 3
progress-bar spec may be added later to `testing/e2e/tests/` as a
visual smoke test.
