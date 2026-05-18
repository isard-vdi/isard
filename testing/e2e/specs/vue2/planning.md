# Planning — Vue 2 admin frontend (old-frontend)

Human-readable functional spec for the **admin planning** flows in the
old frontend (Vue 2, `old-frontend/`). Serves as the contract for the
E2E test `tests/vue2/planning.spec.js`.

The spec focuses on the **Planning** screen (`/planning`) — the
admin-only resource-planner calendar where an administrator creates
and deletes the availability *plannings* that the booking calendar
later consumes.

## Scope

- **Component**: `old-frontend/` (Vue 2 + Vuex + bootstrap-vue).
- **Screens covered**:
  - `pages/Planning.vue` (route `Planning`) — `IsardCalendar` with the
    reservable type/item selectors and `PlanningModal`.
- **Actions covered**:
  - Create a planning for a reservable subitem (profile) over a window
    (`POST /api/v4/item/reservables-planner`).
  - Delete an existing planning (`DELETE
    /api/v4/item/reservables-planner/{plan_id}`).
  - Auto-join: a new planning created contiguous to (or "too close"
    to, after 5-minute rounding) an existing planning's end/start is
    merged into a single planning instead of inserting a second one.
- **Out of scope**:
  - Editing a planning's dates (the `PUT
    /api/v4/item/reservables-planner/{id}/{start}/{end}` button is
    commented out in `PlanningModal.vue`).
  - Non-GPU reservable types (only `gpus` is seeded).
  - The booking side of plannings (covered by `specs/vue2/bookings.md`).
  - Plan integrity / actual-plan / booking-provisioning endpoints.

## Screens, routes and source files

| Screen | Route name | Component | Relevant subcomponents |
| --- | --- | --- | --- |
| Planning | `Planning` | `pages/Planning.vue` | `components/shared/IsardCalendar.vue`, `components/booking/PlanningModal.vue` |

The route `/planning` carries `meta.allowedRoles = ['admin']`; a
non-admin session is bounced by the router guard and never renders the
calendar.

`Planning.vue` behaviour:

- On mount: `setPlannerCurrentCalendarView` (week, past-Monday →
  next-Sunday) then `fetchReservableTypes` →
  `GET /api/v4/items/reservables` (fills the **type** select).
- On type select: `fetchReservableItems` →
  `GET /api/v4/items/reservables/{itemType}` (fills the **item**
  select) and clears the calendar.
- On item select: `fetchPlanning` →
  `GET /api/v4/item/reservables-planner/by-item/{itemId}?start=&end=`
  → existing plannings, each painted by `IsardCalendar` with the
  `unavailable` class and title `"{subitem_id} ({units} units)"`
  (`PlanningUtils.parseEvent`).
- Cell double-click / drag (admin, week|day only — see
  `planningEventsSettings`) opens `PlanningModal` in `create` mode.
- Event click opens `PlanningModal` in `edit` mode (which exposes
  **Delete**).

`PlanningModal` reuses modal id `#eventModal`. Create mode requires
`startDate`, `startTime`, `endDate`, `endTime` and a **profile**
(`#subitemId`) before the **Create event** button
(`.modal-footer button.btn-primary`) dispatches `createPlanningEvent`.
Client-side guards in `createPlanningEvent` reject (`$snotify.info`)
`start < now` (`errors.past-booking`), `end <= start`
(`errors.end-before-start`) and duration `< 5 min`
(`errors.minimum-time`) before any POST.

## Role and common prerequisites

| Element | Expected value |
| --- | --- |
| Component (Compose) | `old-frontend` (active build and deploy) |
| Session | Admin (`adminPerWorker` / `admin_e2e_NN`); `/planning` is admin-only |
| Category | `default` |
| Client language | Irrelevant; assertions read DOM classes/ids and the resolved app i18n, not hardcoded text |
| Seeds | `gpus.json`, `reservables_vgpus.json`, `resource_planner.json` |

### Dedicated planning seed (prerequisite)

`check_plan_item_id_overlapped` rejects (`409 conflict`) any new
planning that overlaps **any** existing planning on the same physical
GPU item (across profiles; GPUs have `planning_item_can_overlap =
False`). The seeded wide plans (`test-t4-2q-available-plan`,
`24ee2910-…`, `test-t4-override-available-plan`, epoch `1e9 → 1e10`)
cover every near-future window on their GPUs, so these specs **must
not** create plannings on `NVIDIA-T4-2Q`, `NVIDIA-A16-2Q` or
`NVIDIA-T4-OVERRIDE`.

These specs require a dedicated GPU device with **no seeded
`resource_planner` row**, so the admin can freely create/delete/join
plannings without colliding with seeds or other workers. It reuses the
existing `gpu_profiles` `NVIDIA/T4` definition (profile
`NVIDIA-T4-2Q`, `units = 8`), so only one seed row is added:

| Seed | Value |
| --- | --- |
| `gpus` | `e2e-gpu-planning` (brand `NVIDIA`, model `T4`, `physical_device: null`, `profiles_enabled: ["NVIDIA-T4-2Q"]`) |
| `reservables_vgpus` | *(none — `list_subitems_enabled` reads `gpu_profiles`, not `reservables_vgpus`)* |
| `resource_planner` | *(none — intentionally empty so the admin owns the whole timeline)* |

The profile id is therefore `NVIDIA-T4-2Q`, but on the **dedicated
device `e2e-gpu-planning`** — `check_plan_item_id_overlapped` keys on
the gpu *device* id, so the seeded wide `test-t4-2q-available-plan`
(on device `c33b8926-…`) does not conflict.

Per-worker time windows keep the single device collision-free across
parallel workers; the specs run in a serial describe. Plan ids created
by each test are stored in `testInfo.annotations` (`type:
"plan-id"`) so `afterEach` deletes them even when assertions fail. The
seeded wide plans must never be deleted.

## Common data

| Field | Example value | Notes |
| --- | --- | --- |
| Reservable type | `gpus` | Only seeded reservable type |
| Reservable item | `e2e-gpu-planning` | Dedicated, plan-free GPU device |
| Profile (subitem) | `NVIDIA-T4-2Q` | Selected in the modal `#subitemId` (on the dedicated device) |
| Planning window | `now + 1h → now + 1h30` (worker-staggered) | Rounded by the backend, see below |
| Rounding | `ROUND_MINUTES = 5` | `start = ceil_dt(start)`, `end = ceil_dt(end) - 1s` |
| Join behaviour (GPU subitem) | `join_before = True`, `join_after = True` | Adjacent same-profile plannings merge |

---

## Scenario P1 — *an administrator creates a planning*

### Given

1. An admin session on `/planning`.
2. The dedicated GPU `e2e-gpu-planning` with profile
   `NVIDIA-T4-2Q` and no seeded planning over the test window.

### When

1. The admin selects reservable type `gpus`
   (`GET /api/v4/items/reservables/gpus` fills the item select).
2. Selects item `e2e-gpu-planning`
   (`GET /api/v4/item/reservables-planner/by-item/<id>` returns `[]`
   → empty calendar).
3. Opens `PlanningModal` in `create` mode (double-click / drag on a
   week cell, or via the store `eventPlanningModalData` with valid
   local times — vue-cal drag is fragile to drive raw).
4. Picks the profile `NVIDIA-T4-2Q` in `#subitemId`, keeps the
   prefilled dates/times (window `now + 1h → now + 1h30`, ≥ 5 min,
   start in the future), presses **Create event**.

### Then

1. `POST /api/v4/item/reservables-planner` is sent with
   `{item_type: "gpus", item_id, subitem_id, start, end}` and responds
   `< 400`, returning the new `plan_id` (tracked as `plan-id`).
2. `createPlanningEvent` clears snotify, resets and closes the modal:
   `#eventModal` is hidden and no `.snotifyToast.snotify-error`
   appears.
3. After the modal closes `Planning.vue` refreshes; the planning is
   painted on the calendar as a `.vuecal__event.unavailable` block
   whose title contains `NVIDIA-T4-2Q`.
4. `GET /api/v4/item/reservables-planner/by-item/<id>` over the window
   now returns exactly one plan with the created `plan_id`, rounded to
   the 5-minute grid (`start = ceil(start)`, `end = ceil(end) - 1s`).

### Error path — invalid window

If the chosen window is in the past, `end <= start`, or shorter than
5 minutes, `createPlanningEvent` shows the corresponding
`$snotify.info` (`components.bookings.errors.past-booking` /
`end-before-start` / `minimum-time`), **no POST** is sent and the
modal stays open.

---

## Scenario P2 — *an administrator deletes a planning*

### Given

1. An admin session on `/planning` with type `gpus` / item
   `e2e-gpu-planning` selected.
2. An existing planning over the test window (created at setup via
   `POST /api/v4/item/reservables-planner`, tracked as `plan-id`).

### When

1. `fetchPlanning` returns the planning; it is painted as a
   `.vuecal__event.unavailable` block.
2. The admin clicks the block → `PlanningModal` opens in `edit` mode
   (dates/profile shown disabled, **Delete** button visible).
3. Presses **Delete** → a `$snotify.prompt` confirmation appears;
   the admin presses **Yes**.

### Then

1. `deletePlanningEvent` shows the transient
   `messages.info.deleting-event` info toast, then
   `DELETE /api/v4/item/reservables-planner/<plan_id>` responds
   `< 400`.
2. snotify is cleared, the modal resets and closes (`#eventModal`
   hidden, no `.snotifyToast.snotify-error`).
3. After refresh the `.vuecal__event.unavailable` block for that
   planning is **gone**.
4. `GET /api/v4/item/reservables-planner/by-item/<id>` over the window
   no longer returns the deleted `plan_id`.

> Note: `delete_plan` also removes the plan's associated bookings.
> This spec deletes a freshly created, booking-free planning so the
> assertion is limited to the planning disappearing.

---

## Scenario P3 — *a planning created too close to another's end is joined*

Covers the auto-merge in `ReservablesPlanner.add_plan`: for a GPU
subitem (`join_before = join_after = True`) a new planning whose
rounded start lands exactly where an existing same-profile planning
ends (or whose rounded end lands exactly where one starts) does **not**
create a second row — the existing planning is stretched to absorb it.

### Mechanics

- `add_plan` stores `start = ceil_dt(start)` and
  `end = ceil_dt(end) - 1s` with `ROUND_MINUTES = 5`.
- `join_existing_plan_before_new_plan_end`: an existing same-profile
  plan with `end == new.start - 1s` has its **end** extended to
  `new.end` (the new plan is *not* inserted; the existing id is
  returned).
- `join_existing_plan_after_new_plan_start`: an existing same-profile
  plan with `start == new.end + 1s` has its **start** moved back to
  `new.start`.
- Because a planning ending at a 5-minute boundary stores `end =
  boundary - 1s` and the next planning starting at that boundary
  stores `start = boundary`, two plannings that are contiguous (or
  whose gap collapses to zero after 5-minute ceil rounding — i.e. the
  second starts within the rounding bucket at the first's end) satisfy
  `existing.end == new.start - 1s` and merge.

### Given

1. An admin session on `/planning`, type `gpus`, item
   `e2e-gpu-planning`, profile `NVIDIA-T4-2Q`.
2. **Planning A** already exists for the window
   `[base, base + 30min)` (created at setup; rounded to the 5-minute
   grid, tracked as `plan-id`).

### When

1. The admin creates **Planning B** for the immediately adjacent
   window `[base + 30min, base + 60min)` (contiguous), or a window
   whose start falls "too close" to A's end so that after 5-minute
   ceil rounding `B.start == A.end + 1s`.
2. `createPlanningEvent` → `POST /api/v4/item/reservables-planner`.

### Then

1. `POST` responds `< 400`. The backend detects the adjacency and runs
   `join_existing_plan_before_new_plan_end` — **Planning A's end is
   extended to B's end**; no second row is inserted.
2. `GET /api/v4/item/reservables-planner/by-item/<id>` over
   `[base, base + 60min]` returns **exactly one** planning (Planning
   A's id), spanning the union `[base, base + 60min)` (rounded), not
   two.
3. The calendar paints a **single** `.vuecal__event.unavailable`
   block covering the whole `[base, base + 60min)` range — there is no
   second block and no visible boundary at `base + 30min`.
4. `afterEach` only needs to delete the surviving merged planning
   (Planning A's id); Planning B's id was never created.

### Variant — non-adjacent stays separate (control)

If Planning B is created with a real gap (e.g. `[base + 45min,
base + 75min)` so that after rounding `B.start > A.end + 1s`), no join
occurs: `by-item` returns **two** plannings and the calendar paints
**two** `.vuecal__event.unavailable` blocks. Both ids are tracked and
deleted.

---

## Cleanup (afterEach)

1. **Plannings** created by the test (`plan-id` in
   `testInfo.annotations`) → `DELETE
   /api/v4/item/reservables-planner/<id>`. After a join only the
   surviving (merged) id needs deleting; a `404` on an absorbed id is
   swallowed.
2. The dedicated GPU/profile seed and all seeded wide plans
   (`test-t4-2q-available-plan`, `24ee2910-…`,
   `test-t4-override-available-plan`) must **not** be deleted.
3. Cleanup errors are swallowed so they don't mask the real cause of
   an earlier failure.

---

## Expected results — global summary

| Scenario | Expected coverage | Key checks |
| --- | --- | --- |
| P1 — Admin creates a planning | ✅ | Modal `Create event` → POST `< 400`, modal closes, no error toast, `.vuecal__event.unavailable` painted, `by-item` returns the new plan |
| P1 — Invalid window | ✅ | Past / `end<=start` / `<5min` → client `.snotify-info`, no POST, modal stays open |
| P2 — Admin deletes a planning | ✅ | Edit modal → Delete → confirm Yes → DELETE `< 400`, block disappears, `by-item` no longer returns the id |
| P3 — Contiguous planning is joined | ✅ | POST `< 400`; `by-item` returns **one** plan spanning the union; **one** calendar block, no boundary at the seam |
| P3 — Non-adjacent stays separate (control) | ✅ | `by-item` returns **two** plans; **two** calendar blocks |

---

## APIs touched by the flows (reference)

- `GET    /api/v4/items/reservables` — reservable types.
- `GET    /api/v4/items/reservables/{itemType}` — items of a type.
- `GET    /api/v4/item/reservable/enabled/{itemType}/{itemId}` —
  subitems (profiles) for the modal select.
- `GET    /api/v4/item/reservables-planner/by-item/{itemId}?start=&end=`
  — plannings for an item overlapping the window.
- `POST   /api/v4/item/reservables-planner` — create a planning
  `{item_type, item_id, subitem_id, start, end}` (admin only).
- `DELETE /api/v4/item/reservables-planner/{plan_id}` — delete a
  planning and its bookings (admin only).

All `reservables-planner` mutations live on the apiv4 `admin_router`;
a non-admin token is rejected before the service runs.

---

## Relevant database state

- **`gpus`**: the physical device (`item_id`) and its
  `profiles_enabled`. GPUs return `planning_item_can_overlap = False`,
  `planning_subitem_can_overlap = True`,
  `planning_subitem_join_before/after = True`,
  `planning_schedule_subitem = True`.
- **`reservables_vgpus`**: the profile (`subitem_id`) and its `units`
  (copied into the created plan via `get_subitem_units`).
- **`resource_planner`**: one row per planning
  `(item_id, subitem_id, start, end, units, event_type="available",
  user_id)`. `add_plan` rounds dates to the 5-minute grid and merges
  adjacent same-`(item_id, subitem_id)` rows instead of inserting
  overlapping/contiguous ones.

---

## Cases not covered (future)

- Editing a planning's window (UI button commented out).
- Deleting a planning that has bookings (cascade) — needs a booking
  fixture and is owned by `specs/vue2/bookings.md`.
- `join_after` direction driven purely from the UI (creating B
  *before* an existing A so A's start moves back) — same mechanic as
  P3, asserted once.
- Overlap conflict (`409`) when creating a planning across a window
  already covered on the same physical GPU.
- Real-time SocketIO `planAdd` / `planDelete` propagation (the store
  reacts via `add_plan` / `remove_plan` but the spec asserts final
  state only).
