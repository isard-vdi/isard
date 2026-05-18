# Testing

IsardVDI has four active test surfaces: APIv4 (FastAPI, pytest),
change-handler (pytest), Go (`go test`), and Playwright E2E against
the live stack. Everything is driven from the repo root through the
`Makefile`, which uses `uv` for every Python entry point.

| Front-end | When to use | What it runs |
|---|---|---|
| `make test-*` | Day-to-day iteration | Runs each suite directly on the host via `uv run` or a targeted Docker one-shot |
| `make ci-*` | Pre-commit / CI parity | Aggregates the same commands `.gitlab-ci.yml` runs (lint + unit tests) |

`docker-compose.ci.yml` was retired once the Python monorepo moved
to a uv workspace: CI jobs now call `uv sync` + `uv run pytest`
directly, and the local `make ci-*` targets do the same so the
toolchain is a single source of truth.

---

## Test layers and boundaries

The suite is built in four layers. Each test should belong to exactly one — if you can't place a test, you probably haven't decided what it's actually verifying.

| Layer | What it proves | Speed | Cost | Coverage |
|---|---|---|---|---|
| **Unit** | One function/class, no network, no DB. Mocks for dependencies. | <1s per test | Low per test, many tests | 60-80% |
| **Integration** | Multiple modules together against a **real DB + real Redis**, no UI. Response shape validation. | 1-10s per test | Medium | 15-30% |
| **Contract** | Pins wire shapes the Pydantic→OpenAPI→SDK→`tsc` pipeline can't catch: `response_model=dict` / v3-compat / hand-built responses, serialization behaviour (e.g. null-omission), and shapes consumed by untyped clients (Flask/Vue 2). Path + status + shape hardcoded. *Not yet built — `testing/contract/` is the planned home.* | <1s per test | Low (few, strict) | only the pipeline's blind spots |
| **E2E** | A user flow through the real browser (Playwright). Click, fill, navigate. | 10-60s per test | High (selectors, races) | 5-10%, critical happy paths only |

Classical pyramid: many unit, some integration, a thin contract net (only the typed-pipeline blind spots — not one per endpoint), very few e2e. E2E are expensive and flaky — don't aim for 200.

### Where each kind lives

```
component/<pkg>/src/<module>/tests/   # unit — co-located with the code
testing/integration/                  # integration — needs a live stack
testing/contract/                     # contract — planned; only pipeline blind-spot endpoints
testing/e2e/                          # e2e — Playwright UI flows
testing/db/                           # shared seed (used by e2e today;
                                      # planned to grow into per-layer fixtures)
```

### Which layer is this test?

| If the test… | …is |
|---|---|
| Calls a pure function and mocks any IO | **unit** |
| Needs Redis or RethinkDB but no UI nor HTTP routing | **integration** |
| Asserts path + status + shape for an endpoint the typed SDK can't already pin | **contract** |
| Opens a page with Playwright and clicks | **e2e** |
| Needs `docker compose` up | **integration** or **e2e**, never unit |
| Takes >10s | Rethink whether you can push it down a layer |

### Call style by layer (SDK vs raw paths)

| Layer / location | Allowed call style |
|---|---|
| `testing/e2e/tests/**/*.spec.js` (UI flows) | Playwright UI selectors only |
| `testing/e2e/fixtures/apiv4/**` (test-issued setup/cleanup) | **Generated SDK** (`testing/e2e/src/gen/apiv4`) |
| `testing/integration/**` | SDK for setup, raw HTTP for the assertions you actually want to pin |
| `testing/contract/**` (new) | **Hardcoded paths** — the whole point of the layer is to pin the wire contract |
| DB seeding (`testing/db/populate_test_db.py`) | RethinkDB directly, no HTTP |
| `bridgeAdminSession` and similar narrow bridges | Raw `page.request` allowed (explicit carve-out) |

The Pydantic→OpenAPI→SDK→`tsc` pipeline already enforces the contract for **typed** consumers: a renamed, removed or retyped field breaks the frontend build when the SDK is regenerated. The contract layer is therefore narrow — it exists only for what that pipeline can't see: `response_model=dict` / v3-compat / hand-built responses, serialization behaviour (e.g. null-omission), and shapes consumed by untyped clients (Flask/Vue 2).

### Code-review block list

- `page.request.<get|post|put|delete|patch>('/api/...')` inside `testing/e2e/tests/**` → block, ask to move into `testing/e2e/fixtures/apiv4/` and call via SDK.
- `requests.<method>('http://...api/v...')` (or equivalent) in `testing/integration/**` test files when the call is part of **setup** → block, ask to add a helper that uses the generated Python SDK.
- Hardcoded paths inside `testing/contract/**` are **expected** — don't flag them.
- `bridgeAdminSession` in `testing/e2e/fixtures/common.js` hits `/isard-admin/login` raw — explicit exception (Flask session bridge, not an `/api/` call).
- Mocks deep enough to neutralise three or more modules in an integration test → block, ask whether it's actually a unit test in disguise.

### Naming conventions

| Layer | Pattern |
|---|---|
| Python unit / integration | `test_<unit_or_topic>.py` |
| Python contract (planned) | `test_<endpoint>_contract.py` |
| Go unit | `*_test.go` (next to the code) |
| Playwright e2e | `*.spec.js` |

---

## Quick Start

```bash
# Full suite (unit + e2e + go)
make test

# The uv-native CI pipeline (mirrors GitLab)
make ci-lint              # format + lint every language
make ci-test              # unit tests: go + python (apiv4, _common, change-handler, changefeed)
make ci-e2e               # Playwright e2e (includes seed)

# Everything except e2e
make ci

# Everything including e2e
make ci-all
```

## Test suites at a glance

| Suite | Tests | How to run locally | CI job |
|---|---:|---|---|
| APIv4 unit | 301 fn | `make test-apiv4` | `unit-test-apiv4` |
| `_common` unit | — | `make test-common` | `unit-test-common` |
| change-handler unit | 66 fn | `make test-change-handler` | `unit-test-change-handler` |
| changefeed unit | — | `make test-changefeed` | `unit-test-changefeed` |
| Go unit | ~60 `*_test.go` | `make test-go` (`go test -race -cover ./...`) | `unit-test-go` |
| Playwright e2e | 76 scenarios | `make test-e2e` (auto-seeds + runs Playwright container) | `test-e2e` |
| Integration (real stack) | — | `make test-e2e-stack` | `integration-real` |

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

### Python unit tests (uv)

Every Python suite runs through `uv run --package <workspace-pkg> pytest`.
The Makefile targets forward `PYTEST_COV_ARGS='__COV__'` to enable
coverage reports under `component/*/src/htmlcov/`:

```bash
make test-python              # all four suites
make test-python-cov          # same, with HTML coverage

make test-apiv4               # API v4 only
make test-common              # isardvdi_common only
make test-change-handler      # change-handler only
make test-changefeed          # changefeed only
```

Tests live at `component/<pkg>/src/<module>/tests/`. They use:

- `pytest` + `pytest-asyncio` + `httpx`
- FastAPI `TestClient`
- `rethinkdb-mock` fork (`isard-vdi/rethinkdb-mock@core-document-manipulation`)
- Service-level `monkeypatch` for endpoint isolation
- `app.dependency_overrides` for `Depends()` bypass

APIv4 current count: **301 test functions** across **34 files**
covering roughly 35–40% of the 632 endpoints.

### change-handler tests

Pure-unit scope (mock `socketio_server`, patch external libs). Tests
live at `component/change-handler/src/isardvdi_change_handler/tests/` — one file
per handler, 13 handlers, 66 tests total. They pin the SocketIO
event name, namespace, and room for every insert / update / delete path.

### Engine tests

```bash
make test-engine
```

Runs inside the live `isard-engine` container because the engine
imports `libvirt` + `pci` + `paramiko` at module load.

### Go tests

```bash
make test-go                                   # unit tests with race + coverage
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

### Isolated e2e stack (CI parity)

```bash
make down                  # stop dev stack
make test-e2e-stack        # build + bring up docker-compose.e2e.yml + seed + Playwright
make test-e2e-stack-restore  # tear everything down and bring dev stack back
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

component/change-handler/src/isardvdi_change_handler/tests/
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

Each language has a granular `make lint-*` target that maps 1-to-1
to its `.gitlab-ci.yml` job. `make lint` runs all of them:

```bash
make lint                 # every linter

make lint-python          # uv run isort --check . && uv run black --check .
make lint-system-deps     # Dockerfile ↔ pyproject [tool.isardvdi.system-deps] coherence
make lint-go              # golangci-lint fmt --diff
make lint-frontend        # component/frontend (Reka + Tailwind + Bun)
make lint-old-frontend    # old-frontend (Vue 2)
make lint-protobuf        # buf lint + buf breaking
```

Auto-fixers follow the same naming:

```bash
make format               # everything

make format-python        # uv run isort . && uv run black .
make format-frontend      # bun run format + lint:fix
make format-old-frontend  # bun run lint --fix
```

Tool versions are pinned in `pyproject.toml` (Python dev group) and
`.gitlab-ci.yml` (everything else). If you install linters on the
host, match those versions or your checks may diverge from CI — the
`isardvdi-commit` skill (`~/.claude/skills/isardvdi-commit`) reads
them live for each commit run.

## Git hooks

```bash
make setup-hooks          # git config core.hooksPath .githooks
```

- `.githooks/pre-commit` runs the `lint-*` targets relevant to the
  files you staged (Python, frontend, proto, system-deps).
- `.githooks/pre-push` runs `make test-python test-go` so you
  don't push a broken unit test.

## CI alignment

`.gitlab-ci.yml` and the `make ci-*` targets call the same uv / go /
bun commands. Passing `make ci` locally means the corresponding
GitLab jobs will pass. If you need a change reflected in CI, edit
both places — there is no longer a separate `docker-compose.ci.yml`
to keep in sync.

## See also

- `migration/TESTS_TODO.md` — prioritised backlog of tests still to write.
- `TEST_COVERAGE_ANALYSIS.md` (repo root) — per-file coverage map for every suite.
- `testing/DEPLOYMENT_TESTS.md` — deployment-specific integration tests.
