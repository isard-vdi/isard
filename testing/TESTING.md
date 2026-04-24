# Testing

IsardVDI has four active test surfaces: APIv4 (FastAPI, pytest),
change-handler (pytest), Go (`go test`), and Playwright E2E against
the live stack. Everything is driven from the repo root via two
parallel front-ends:

| Front-end | When to use | What it runs |
|---|---|---|
| `make test-*` | Day-to-day iteration | Runs each suite directly on the host or via a targeted Docker one-shot |
| `make ci-*` (via `docker-compose.ci.yml`) | Pre-commit / CI parity | Runs each suite inside the exact same image + env the GitLab pipeline uses |

**Golden rule**: before pushing, run the `ci-*` target that covers
the code you touched. Passing locally means passing in CI.

---

## Quick Start

```bash
# Full suite (legacy — unit + e2e + go)
make test

# The three-stage CI pipeline (what GitLab runs)
make ci-lint              # format + lint every language
make ci-test              # unit tests: apiv4, go, codegen freshness
make ci-integration-test  # integration: change-handler, apiv4, go
make ci-e2e               # Playwright e2e (includes seed)

# Everything except e2e
make ci

# Everything including e2e
make ci-all
```

## Test suites at a glance

| Suite | Tests | How to run locally | CI equivalent |
|---|---:|---|---|
| APIv4 unit (routes) | 301 fn | `make test-apiv4` | `docker compose -f docker-compose.ci.yml run --rm unit-test-apiv4` |
| APIv4 integration | varies | — | `docker compose -f docker-compose.ci.yml run --rm integration-test-apiv4` |
| change-handler | 66 fn | — | `docker compose -f docker-compose.ci.yml run --rm integration-test-change-handler` |
| Go unit | ~60 `*_test.go` | `make test-go` (`go test -race -cover ./...`) | `docker compose -f docker-compose.ci.yml run --rm unit-test-go` |
| Go integration | — | — | `docker compose -f docker-compose.ci.yml run --rm integration-test-go` |
| Playwright e2e | 76 scenarios | `make test-e2e` (auto-seeds + runs Playwright container) | `make ci-e2e` |

### E2E scenario breakdown (76 total)

- `tests/login.spec.js` — 23 scenarios (form, SAML, LDAP, redirects, maintenance)
- `tests/desktops.spec.js` — 27+1 scenarios (Vue 3 desktop cards, actions, bookings, bastion)
- `tests/vue3-navigation.spec.js` — 11 scenarios (authenticated-route smoke + unauthenticated guards)
- `tests/vue3-profile.spec.js` — 4 scenarios (user details, password modal, api-key, console-error baseline)
- `tests/vue3-templates.spec.js` — 3 scenarios (list, user/shared tabs, new-template)
- `tests/vue3-deployments.spec.js` — 3 scenarios (list, stepper form, admin role gate)
- `tests/vue3-recycle-bin.spec.js` — 2 scenarios (load + empty/table state)
- `tests/vue3-media.spec.js` — 3 scenarios (load, tabs, new-media control)

---

## Prerequisites

### 1. Running stack

```bash
docker compose up -d
docker compose ps   # verify everything is Running
```

### 2. Seeded DB

Tests expect a populated RethinkDB with the fixtures in
`testing/db/data/*.json` — in particular `admin_e2e_01..15` and
`user_e2e_01` for parallel-worker isolation.

`make test-e2e` auto-runs `test-e2e-seed` first, but you can seed
separately:

```bash
make test-e2e-seed
# or, direct:
python3 testing/db/populate_test_db.py
```

The seeder upserts by primary key, so re-running is idempotent.

### 3. `PROXY_PROTOCOL` must be off for local browser-based tests

`isardvdi.cfg.example` leaves `PROXY_PROTOCOL=true`. With that value
HAProxy's external frontend requires a PROXY v2 header on every TCP
connection — browsers and `curl` don't send one, so Playwright
can't reach the portal.

For local e2e runs, confirm your `isardvdi.cfg` has:

```
PROXY_PROTOCOL=false
```

…then rebuild + recreate the portal:

```bash
bash build.sh                                # regenerates docker-compose.yml
docker compose up -d --force-recreate isard-portal
```

The portal entrypoint unsets the variable when not exactly `"true"`
(see `docker/haproxy/_common/haproxy-docker-entrypoint.sh`), so
`PROXY_PROTOCOL=false` and leaving it unset both work.

### 4. Optional identity providers

Some spec files exercise external flows:

- SAML: `isard-authentication-test-saml` (SimpleSAML IdP) — auto-started by the default `docker compose up`.
- LDAP: `isard-authentication-test-ldap` (Planet Express test directory) — auto-started.

If either container is absent the matching scenarios in
`login.spec.js` fail or time out. The rest of the suite is
unaffected.

---

## Running tests

### APIv4 unit tests

```bash
# Direct: installs rethinkdb-mock + pytest deps into the running isard-apiv4 container
make test-apiv4

# CI-parity
docker compose -f docker-compose.ci.yml run --rm unit-test-apiv4
```

Tests live at `component/apiv4/src/api/routes/tests/`. They use:

- `pytest` + `pytest-asyncio` + `httpx`
- FastAPI `TestClient`
- `rethinkdb-mock` fork (`isard-vdi/rethinkdb-mock@core-document-manipulation`)
- Service-level `monkeypatch` for endpoint isolation
- `app.dependency_overrides` for `Depends()` bypass

Current count: **301 test functions** across **34 files** covering roughly 35–40% of the 632 endpoints.

### change-handler tests

```bash
docker compose -f docker-compose.ci.yml run --rm integration-test-change-handler
```

Pure-unit scope (mock `socketio_server`, patch external libs). Tests
live at `component/change-handler/src/tests/` — one file per handler,
13 handlers, 66 tests total. They pin the SocketIO event name,
namespace, and room for every insert / update / delete path.

### Go tests

```bash
# Direct
make test-go

# CI-parity
docker compose -f docker-compose.ci.yml run --rm unit-test-go
docker compose -f docker-compose.ci.yml run --rm integration-test-go
```

### Playwright E2E

```bash
# Default: 4 workers, screenshots on failure, chromium
make test-e2e

# Fast (no artefacts)
E2E_SCREENSHOT=off E2E_TRACE=off E2E_WORKERS=8 make test-e2e

# Full debug (all artefacts)
E2E_SCREENSHOT=on E2E_TRACE=on E2E_VIDEO=on make test-e2e

# Specific browser
E2E_BROWSER=firefox make test-e2e
E2E_BROWSER=all     make test-e2e  # chromium + firefox

# Remote target
E2E_BASE_URL=https://staging.example.com make test-e2e

# Local dev against an unseeded DB / different admin password
E2E_ADMIN_USERNAME=admin \
E2E_ADMIN_PASSWORD="$(grep ^WEBAPP_ADMIN_PWD isardvdi.cfg | cut -d= -f2)" \
E2E_WORKERS=1 \
  ./testing/e2e/node_modules/.bin/playwright test tests/vue3-*.spec.js
```

Run without `make` (Docker directly, matches CI exactly):

```bash
cd testing/e2e && yarn
docker run --rm --ipc=host --network=host \
  -v "$(pwd):/e2e" -w "/e2e" \
  mcr.microsoft.com/playwright:v1.57.0-jammy \
  yarn playwright test --reporter=list
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `E2E_BASE_URL` | Base URL override | `https://localhost` (`https://host.docker.internal` if `DOCKER=1`) |
| `E2E_BROWSER` | `chromium` / `firefox` / `all` | `chromium` |
| `E2E_WORKERS` | Parallel workers | 16 (CI: 2) |
| `E2E_RETRIES` | Retries on failure | 1 (CI: 2) |
| `E2E_TIMEOUT` | Per-test timeout (ms) | 30000 |
| `E2E_REPORTER` | `html` / `list` / `line` / `dot` | `html` |
| `E2E_SCREENSHOT` | `on` / `only-on-failure` / `off` | `only-on-failure` |
| `E2E_TRACE` | `on` / `off` / `on-first-retry` / `retain-on-failure` | `on-first-retry` |
| `E2E_VIDEO` | `on` / `off` / `on-first-retry` / `retain-on-failure` | `off` |
| `E2E_ADMIN_USERNAME` | Override `admin` fixture username | `admin` |
| `E2E_ADMIN_PASSWORD` | Override `admin` fixture password | `IsardVDI` (fixture default) |

### Parallel workers and test-user isolation

The seeded DB carries `admin_e2e_01..15` + `user_e2e_01` so each
worker has its own account. If you run against a non-seeded DB set
`E2E_WORKERS=1` — multiple workers sharing one admin race on
session state.

Vue 3 view specs (`vue3-*.spec.js`) all use the `admin` fixture user
and are serial-safe even in parallel runs.

---

## File layout

```
testing/e2e/
├── playwright.config.ts        # env-driven (see table above)
├── package.json                # @playwright/test 1.57.0
├── fixtures/
│   ├── common.js               # checkNoRouterErrors
│   ├── login.js                # users/categories/SAML/LDAP/groups + loginHelpers
│   └── desktops.js             # desktop test data + helpers
└── tests/
    ├── login.spec.js
    ├── desktops.spec.js
    ├── vue3-navigation.spec.js
    ├── vue3-profile.spec.js
    ├── vue3-templates.spec.js
    ├── vue3-deployments.spec.js
    ├── vue3-recycle-bin.spec.js
    └── vue3-media.spec.js

component/change-handler/src/tests/
├── test_base_handler.py        # lifecycle + datetime / json helpers
├── test_domains_handler.py     # kind routing + engine-status filter
├── test_resources_handler.py   # graphics / videos / etc. admins emit
├── test_bookings_handler.py
├── test_categories_handler.py
├── test_deployments_handler.py
├── test_groups_handler.py
├── test_hypervisors_handler.py
├── test_media_handler.py
├── test_resource_planner_handler.py
├── test_targets_handler.py
├── test_users_handler.py
└── test_vgpus_handler.py

testing/db/
├── populate_test_db.py         # idempotent seeder
└── data/*.json                 # users, categories, groups, domains, …
```

## Test data

Seed JSON files in `testing/db/data/`:

- `users.json` — all test users with bcrypt-hashed passwords, categories, roles. Includes `admin_e2e_01..15` + `user_e2e_01` for parallel e2e isolation.
- `categories.json` — default, hidden, email, another, maintenance, disclaimer, notifications, password_reset.
- `groups.json` — enrollment codes mapped to (category, role).
- `domains.json` — desktops + templates in every relevant status (Started, Stopped, Failed, Maintenance, Downloading…).
- `authentication.json` — per-category auth policy.

To add a new fixture, update the matching JSON and re-run `make
test-e2e-seed`.

## Linting

Run the linters `make ci-lint` runs:

```bash
# Python — apiv4, _common, change-handler, etc.
docker compose -f docker-compose.ci.yml run --rm check-python

# Vue 3 frontend (Reka + Tailwind)
docker compose -f docker-compose.ci.yml run --rm check-frontend

# Vue 2 (old-frontend)
docker compose -f docker-compose.ci.yml run --rm check-old-frontend

# Protobuf
docker compose -f docker-compose.ci.yml run --rm check-protobuf
```

Auto-fixers live under the `fix` profile:

```bash
docker compose -f docker-compose.ci.yml --profile fix up
# or direct:
docker compose -f docker-compose.ci.yml run --rm fix-python
docker compose -f docker-compose.ci.yml run --rm fix-old-frontend
```

Tool versions are pinned in `.gitlab-ci.yml`. If you install linters
on the host, match those versions or your checks may diverge from
CI — the `isardvdi-commit` skill (`~/.claude/skills/isardvdi-commit`)
reads them live for each commit run.

## CI alignment

`docker-compose.ci.yml` mirrors `.gitlab-ci.yml` one-to-one:

- Same images, envs, commands.
- Tests share a `/ci-results` volume with XUnit + log output.
- `profiles: [integration-test]` / `[fix]` group the one-shots so
  they don't start in a plain `docker compose up`.

Passing a service locally means the same GitLab job passes. **Do
not** edit `docker-compose.ci.yml` just to make a test go green —
the GitLab pipeline won't pick up the change.

## See also

- `migration/TESTS_TODO.md` — prioritised backlog of tests still to write.
- `TEST_COVERAGE_ANALYSIS.md` (repo root) — per-file coverage map for every suite.
- `testing/DEPLOYMENT_TESTS.md` — deployment-specific integration tests.
