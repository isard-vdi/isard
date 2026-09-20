# Desktop create races the reconcile self-heal (#3391)

Functional specification for the regression test `tests/webapp/desktop_create_race.spec.js`.

## Context

- **Endpoint**: `POST /api/v4/item/desktop` (persistent desktop from a template) —
  `CommonDesktops.new_from_template` → `Storage.enqueue_disk_creation_chain_for_domain`.
- **Bug**: while apiv4 parked the new domain (`CreatingDisk`) and storage (`maintenance`)
  and then registered the disk-create task, a change-handler reconcile tick landing in that
  gap re-issued `find`/`check_backing_chain` on the still-unregistered storage. apiv4's own
  `create_task` then found that task pending and answered `428 storage_pending_task`; nothing
  was rolled back, so the desktop stranded `Failed` with its storage `deleted` and its name
  taken, and the user's retry got a 409.
- **Fix**: register the task before parking (storage model), a `status_time` grace in the
  reconcile passes (change-handler), and a rollback in `new_from_template` when the chain
  refuses (common).

## Roles and preconditions

| Item | Expected value |
| --- | --- |
| Client | Authenticated admin (advanced privileges create persistent desktops) |
| Template | Seeded `template-test-001`, ready storage, default category |
| Initial state | Stack healthy; hypervisor Online with a storage pool |

## Scenario

1. Create five persistent desktops from the template in sequence, each with a unique name.
2. Each `createDesktop` must succeed (never `428 storage_pending_task`).
3. Each desktop must reach **Stopped**, never **Failed**.
4. Created desktops are tracked and deleted in teardown.

## Reconcile pressure (how the regression is actually exercised)

The e2e runner has no docker socket, so the spec cannot start the reconcile amplifier itself.
On staging the spec is run while the amplifier
(`docker exec isard-change-handler python3 /tmp/amplify.py`) drives
`_reconcile_stuck_storage` + `_reconcile_stuck_domains` in a tight loop, reproducing the
production tick continuously. With the fix every create still reaches Stopped; reverting the
fix and re-running makes the create 428 or the desktop end Failed (the control).

## Rollback (fix C) note

The refusal branch that fix C cleans up (`new_from_template` deleting the domain and the
un-owned storage so the name frees) cannot be triggered deterministically through official e2e
paths — it needs the reconcile to land at a precise instant, which is non-deterministic. It is
covered by the unit suite `component/_common/tests/lib/domains/desktops/test_new_from_template_rollback.py`
and by the live control on staging (428 with the fix reverted leaves zero rows and the same name
recreates).
