# APIv4 endpoint audit harness

Probes every in-scope apiv4 route with a realistic payload, records the
response, and reports failures grouped by traceback signature.

In scope (per the approved plan in `~/.claude/plans/lovely-herding-pine.md`):
- every `/api/v4/admin/**` route
- the top-50 high-traffic endpoints called by webapp/Vue 2/Vue 3 (listed
  in `route_filter.py::TOP_50_FRONTEND_ROUTES`)

Out of scope (skipped):
- multipart/form-data endpoints (audit only sends JSON in v1)
- endpoints that flip global state (maintenance toggles, etc.)
- specialty routers (register / password_reset / disclaimer / direct_viewer)

## How to run

```bash
docker run --rm --network isard-network -v /opt/isard/src:/src -w /src \
  -e E2E_ADMIN_USER=admin_e2e_01 -e E2E_ADMIN_PWD='IsardTest1!' \
  python:3.12-slim bash -c '
    pip install --quiet -r testing/integration/requirements.txt >/dev/null 2>&1
    cd testing && pytest integration/audit/ -m audit -v --tb=line --maxfail=0
  '
```

After the run, `testing/integration/audit/audit_report.md` and
`audit_report.csv` are written. Open the .md to see signatures grouped
by frequency.

## How to fix

For each top-frequency signature in the report:

1. Reproduce with a single endpoint via `IsardClient` + a quick probe
   script (mirror the pattern from `/tmp/audit_users.py` we wrote
   earlier — see `~/.claude/skills/isardvdi-apiv4/`).
2. Find the broken call site in `component/apiv4/src/api/services/*.py`
   or `component/_common/isardvdi_common/`.
3. Fix per the patterns in the migration skill / today's commits
   (`cf0e124a5`, `bc9a34fc3`, `71bd544bc`).
4. Re-run a scoped audit:
   ```
   pytest integration/audit/ -m audit -k '<path-substring>'
   ```
5. Land one commit per signature (subject names the signature; body
   lists the affected endpoints).

## Files

- `payload_factory.py` — OpenAPI schema → minimal valid payload (~80 LOC,
  no external deps)
- `frontend_overrides.py` — hand-curated payloads for top-N admin routes;
  fall through to `payload_factory` when no override
- `route_filter.py` — picks which routes to include; lists the top-50
  frontend routes + skip lists
- `error_classifier.py` — extracts (exception_class, location, msg) from
  response body's `debug` field; produces stable bucket keys
- `report.py` — Markdown + CSV output
- `conftest.py` — session fixtures: `openapi_spec`, `scratch_entities`,
  `audit_results` (autouse-flushed to disk at teardown)
- `test_audit_endpoints.py` — single parametrized test that probes every
  route; records all results, fails only on 5xx

## Limitations (v1)

- No multipart support. Hypervisor POST and file-upload endpoints are
  listed in `route_filter::SKIPPED_FORM_DATA`.
- Path-parameter substitution uses heuristic defaults from
  `ScratchEntities.as_path_params()`. Routes whose parameter names aren't
  in that map get the literal string `"x"`, which usually 404s — those
  show up as expected 4xx, not bugs.
- 5xx with `LOG_LEVEL != DEBUG` only surfaces a generic
  "internal_server" message; set `LOG_LEVEL=DEBUG` on the apiv4
  container before running for full tracebacks.
