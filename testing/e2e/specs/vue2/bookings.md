# Bookings — Vue 2 user frontend (old-frontend)

Human-readable functional spec for the **GPU bookings** user flows in
the old frontend (Vue 2, `old-frontend/`). Serves as the contract for
the E2E test `tests/vue2/bookings.spec.js`.

The spec focuses on the **Booking** screen (`/bookings/desktop/:id`)
— the plans-and-bookings calendar for a desktop with a GPU.

## Scope

- **Component**: `old-frontend/` (Vue 2 + Vuex + bootstrap-vue).
- **Screens covered**:
  - `Booking.vue` (route `booking`) — `IsardCalendar` calendar with
    `EventModal`.
- **Actions covered**:
  - Create a booking on a desktop with a GPU when a
    `resource_planner` covers the window
    (`POST /api/v4/item/booking/event`).
  - Behaviour when there is no plan / no units available (no
    `available` strips are rendered on the calendar).
  - Override other users' bookings when the caller's priority rule has
    a higher `priority` than the existing booking (orange
    `overridable` strip).
  - Calendar showing gaps when an interval of the plan has all units
    booked (gap in the `available` strip).
- **Out of scope**:
  - **Deployment** bookings (the same `Booking.vue` screen accepts
    `type=deployment`, but the Vue 2 tests limit themselves to
    desktops because deployments are an *advanced*-role concern and
    the current seed does not provide one with a GPU).
  - Inline editing of an existing booking (the button is commented out
    inside `EventModal.vue`).
  - Cancelling an in-progress booking (covered by apiv4 tests).
  - StartNowModal and the "start now" window — the calendar invokes
    them but this spec only covers the scheduled-booking case.

## Screens, routes and source files

| Screen | Route name | Component | Relevant subcomponent |
| --- | --- | --- | --- |
| Booking | `booking` | `pages/Booking.vue` | `components/shared/IsardCalendar.vue`, `components/booking/EventModal.vue` |

`Booking.vue` calls, on `onMounted`:

- `fetchEvents` →
  `GET /api/v4/item/booking/get-desktop/{id}?startDate=&endDate=&returnType=all`.
  Response: a combined array of **bookings** (`event_type: "event"`)
  and **plans** (`event_type ∈ {"available", "overridable",
  "unavailable"}`) already merged by
  `BookingsProcessed.get_item_bookings`.
- `fetchPriority` →
  `GET /api/v4/items/bookings/get-priority-desktop/{id}`. Response:
  `{name, forbid_time, max_time, max_items}` — stored and consumed by
  `BookingUtils.priorityAllowed` to enable/disable the create action.

`get_item_availability` skips intervals with
`event_type == "unavailable"` when `returnUnavailable` is `False`
(the default, and what `get_item_bookings` uses). As a result,
**saturated intervals never reach the frontend and the calendar shows a
gap** between `available` strips (see Scenario 4).

## Role and common prerequisites

| Element | Expected value |
| --- | --- |
| Component (Compose) | `old-frontend` (active build and deploy; without it, `goto('/')` does not even load Vue 2) |
| Session | Started via the `login.js` fixture according to the role each scenario requires |
| Category | `default` by default; tests with non-admin users use `user_e2e_01` (role `user`) |
| Client language | Irrelevant; tests only read text via translations of `forms.domain.bookables.vgpus` and `components.bookings.*` |
| Seeds | `reservables_vgpus.json`, `bookings_priority.json`, `resource_planner.json`, `gpus.json`, `users.json`, `bookings.json` (see list at the end) |

## Common data

| Field | Example value | Notes |
| --- | --- | --- |
| New desktop name | `e2e-vue2-gpu-<worker>-<timestamp>` | Backend pattern (`name_pattern_or_400` in apiv4) |
| GPU shared with `user` | `NVIDIA-T4-2Q` | Seed with `allowed.roles = ["admin", "user"]` |
| Single-unit override GPU | `NVIDIA-T4-OVERRIDE` | `total_units = 1`, `priority_id = "test-override-rule"`, roles `["advanced","user"]` (S3) |
| Advanced user | `advanced_e2e_01` | Role `advanced`, category `default`, priority `800` on `NVIDIA-T4-OVERRIDE` (S3) |
| GPU admin-only | `NVIDIA-A16-2Q` | Seed with `allowed.roles = ["admin"]` |
| "No" GPU | `None` | Sentinel seed; always visible to every role |
| Plan with availability | `test-t4-2q-available-plan` for `NVIDIA-T4-2Q` | Covers the whole range `epoch_time 1e9 → 1e10` (≈ 2001 → 2286) |
| Future test booking | Created by the test via `POST /api/v4/item/booking/event` | The test uses a window `now+1h → now+2h` |
| Admin `forbid_time` | 1 minute (seed `default admins`) | Allows creating bookings that start almost immediately |
| User `forbid_time` | 15 minutes (seed `test-low-forbid-time`) | Margin needed to avoid the *forbid* branch in this spec |

The `desktop_id`, `booking_id` and `priority_id` created by each test
are stored in `testInfo.annotations` (`type ∈ {"desktop-id",
"booking-id", "priority-id"}`) so `afterEach` can delete them even when
the assertions fail.

---

## Scenario 1 — *a user can add a booking on a desktop with a GPU when a plan exists*

Covers statement 3 of the *user story*.

### Given

1. A desktop owned by the test user with
   `reservables.vgpus = ["NVIDIA-T4-2Q"]` exists (created at setup
   via `POST /api/v4/item/desktop`).
2. The seed `resource_planner.json` provides the plan
   `test-t4-2q-available-plan` (`event_type = "available"`, `units =
   8`, `start.epoch_time = 1000000000`, `end.epoch_time =
   10000000000`) for `NVIDIA-T4-2Q`. This plan covers any reasonable
   window from `now`.
3. The priority rule assigned to the `NVIDIA-T4-2Q` *bookable* is
   `test-booking-rule` (seed `test-low-forbid-time`, `forbid_time =
   15`, `max_time = 120`, `max_items = 2`).

### When

1. The user navigates to `/bookings/desktop/<id>` (the **Book** action
   from the desktop card; Card.vue's handler pushes the `booking`
   route with `params={id, type:"desktop"}`).
2. `Booking.vue` loads:
   - `GET /api/v4/item/booking/get-desktop/<id>?startDate=&endDate=&returnType=all`
     → the calendar events (green *availability* split for the plan
     and empty *bookings* split since the user has none yet).
   - `GET /api/v4/items/bookings/get-priority-desktop/<id>` → the
     priority `{forbid_time:15, max_time:120, max_items:2, name}`.
3. Picks a slot in the *bookings* split: double-click + drag on a
   calendar cell (interval ≥ `now + 16 min` and duration ≤
   `120 min` so `priorityAllowed` passes).
4. The `#eventModal` modal opens in `create` mode with the dates
   pre-filled from the selection.
5. Types a title (e.g.
   `e2e-vue2-booking-<worker>-<timestamp>`) and presses **Create**.

### Then

1. The call `POST /api/v4/item/booking/event` receives a body with:
   - `item_id` = the desktop's `id`.
   - `item_type` = `"desktop"`.
   - `start` / `end` in UTC ISO.
   - `title` = the entered title.
   Responds `< 400` and returns the `booking_id`. It is stored in
   `testInfo.annotations` (`type: "booking-id"`).
2. The modal closes, `Booking.vue` calls `fetchEvents` again and the
   chosen slot appears in the *bookings* split (`event` color, blue).
3. If the user queries `GET /api/v4/items/bookings`, the new entry is
   there (covers `BookingsSummary.vue`, not exercised here).

### Error path — *priority* does not allow

The three priority-violation cases (`forbid_time`, `max_time`,
`max_items`) have their own numbered scenarios: see **S5** (forbid
time), **S6** (max items) and **S7** (max time).

---

## Scenario 2 — *a user cannot create a booking when no GPU is available*

Covers statement 4 of the *user story*. "No GPU available" covers two
different cases that the UI treats the same observable way (*no green
strip appears on the calendar*) but with different origins in the
backend.

### Case 2a — the desktop has a GPU but its `subitem_id` has no plan

#### Given

1. The test creates (at setup) a mock GPU or reuses an existing one
   without a `resource_planner`. **Case reproducible with the seed**:
   there are bookables/seeds with GPU `NVIDIA-A16-4Q` that exists as a
   vGPU but for which the seed provides no `resource_planner` (only
   `NVIDIA-A16-2Q` and `NVIDIA-T4-2Q` are seeded). The setup desktop
   has `reservables.vgpus = ["NVIDIA-A16-4Q"]`.
   - If the test user is not authorised to `NVIDIA-A16-4Q` (role
     `user`), this case is exercised as **admin**
     (`adminPerWorker`) to avoid the allowed barrier.

#### When

1. The user (admin) opens `/bookings/desktop/<id>` for this desktop.
2. `fetchEvents` returns **0 events** of type `available`
   (`get_item_availability` produces no interval because
   `get_subitems_planning` finds nothing).

#### Then

1. The calendar renders the *availability* split with no green strip.
   The whole schedule is empty.
2. If the user tries to pick a cell in the *bookings* split,
   `BookingUtils.canCreate` returns `true` (no overlapping `event`)
   **but** when the frontend sends
   `POST /api/v4/item/booking/event`, the backend responds `4xx`
   because `ReservablesPlannerProccess.new_booking_plans` finds no
   matching plan. The handler shows `ErrorUtils.handleErrors` (snotify
   `components.bookings.errors.*` per the backend description).

> Note: the client-side `canCreate=false` branch does not fire here
> because there are no events with `event_type ∈ {available,
> overridable}` to compare against. The UI has **no** local guard;
> the backend is the final authority, and the test must assert that
> the response is `4xx` and that no new event appears on the calendar.

### Case 2b — the desktop has no GPU assigned

#### Given

1. The desktop has `reservables.vgpus = []` or `["None"]`.

#### When

1. The user tries to navigate to `/bookings/desktop/<id>`.

#### Then

1. The call `GET /api/v4/item/booking/get-desktop/<id>` returns
   `[]` (no booking and no plan: the desktop has no reservable GPU).
2. The calendar renders both splits empty.
3. The call `get-priority-desktop/<id>` returns `{forbid_time:0,
   max_time:0, max_items:0}` because there is no *bookable* against
   which to compute priority.
4. `BookingUtils.priorityAllowed` returns `false` (the `forbid_time =
   0` always passes, but `max_time = 0` makes any duration > 0 break
   `checkMaxTime`). `$snotify` shows
   `components.bookings.errors.maximum-time` and no POST is sent.

---

## Scenario 3 — *a user with higher priority overrides existing bookings of lower priority (and a lower-priority one cannot)*

Covers statement 5 of the *user story*.

### Why a dedicated bookable

The shared `NVIDIA-T4-2Q` cannot prove role-based override: its rule
set (`test-booking-rule`) has a single row whose `allowed.users` is
`[]`. In `user_matches_priority_rule` the `users` dimension is checked
before `roles`, and an empty list matches **everyone**, so every role
resolves to the same priority (`500`) on that GPU — no override can
ever fire.

The seed therefore adds a dedicated, single-unit bookable:

| Seed | Value |
| --- | --- |
| `reservables_vgpus` | `NVIDIA-T4-OVERRIDE` — `total_units = 1`, `allowed.roles = ["advanced","user"]`, `priority_id = "test-override-rule"` |
| `gpus` | `e2e-gpu-override-t4` device exposing the `NVIDIA-T4-OVERRIDE` profile |
| `resource_planner` | `test-t4-override-available-plan` — `units = 1`, wide range |
| `bookings_priority` | `test-override-advanced` (role `advanced`, priority `800`) and `test-override-user` (role `user`, priority `300`); `users`/`groups`/`categories` set to `false` so role matching is actually reached |
| `users` | `advanced_e2e_01` (role `advanced`, category `default`, password `IsardTest1!`) |

Per-worker booking windows keep the single unit collision-free across
parallel workers (`workerBookingWindow`); the two specs run in a
serial describe.

> Backend fix enabling this: `count_non_overridable_bookings` now
> blocks on `priority >= caller` (was `<=`), and
> `compute_overridable_bookings` / `join_consecutive_plans` preserve
> the `available`/`overridable`/`unavailable` classification instead
> of flattening it to `available`. The *loser's* booking row is still
> not deleted on create (eviction is a scheduler concern, not
> asserted here).

### S3a — advanced (800) overrides user (300)

1. `user_e2e_01` creates a booking on `NVIDIA-T4-OVERRIDE` for the
   window (setup via API; priority `300`).
2. `advanced_e2e_01` opens `/booking/desktop/<adv-desktop-id>`.
   `fetchEvents` returns the conflicting slot as
   `event_type = "overridable"` (`300 < 800`), painted orange by
   `IsardCalendar.vue` (`.vuecal__event.overridable`).
3. The advanced caller presses **Create** over that window.

**Then:** `POST` responds `< 400` (the higher-priority caller is
allowed onto the unit), the modal closes, no error toast appears, and
the advanced booking is painted in the *bookings* split
(`.vuecal__event.event` by title).

### S3b — user (300) cannot override advanced (800)

1. `advanced_e2e_01` creates a booking on `NVIDIA-T4-OVERRIDE` for the
   window (setup via API; priority `800`).
2. `user_e2e_01` opens `/booking/desktop/<user-desktop-id>`. The slot
   is `unavailable` for priority `300` (`800` is not `< 300`), so it
   is filtered out — the calendar paints **no** `.overridable` strip
   over the window.
3. The user presses **Create** over that window.

**Then:** `POST` responds `4xx` (`booking_does_not_fit_date`),
`ErrorUtils.handleErrors` shows `.snotify-error`, the modal stays
open, no booking is painted, and the advanced booking remains intact
(verified via the feed).

### S3c — advanced (800) books a wider window over an overridable booking in the middle

1. `user_e2e_01` creates a 30-min booking (priority `300`) sitting in
   the middle of a wider 90-min window.
2. `advanced_e2e_01` opens its desktop calendar: the middle segment is
   `overridable`, with `available` margins on each side.
3. The advanced caller creates the full 90-min booking.

**Then:** `POST` responds `< 400` (the middle overridable booking does
not block the higher-priority caller), the modal closes, no error
toast, and the wider booking is painted in the *bookings* split.

---

## Scenario 4 — *when all units of a GPU are booked, the calendar shows gaps in the corresponding range*

Covers statement 6 of the *user story*. Here "gap" means *the absence
of a green `available` strip in the availability split* within a
specific plan window, **not** a different event.

### Given

1. A plan `test-t4-2q-available-plan` exists with `units = 8` that
   covers `now → now + N hours`.
2. (At setup, via API) **8 simultaneous bookings** are created on
   `NVIDIA-T4-2Q` that occupy the window `[now+1h, now+2h]` with
   `units = 1` each and `priority = 999` (admin to guarantee they are
   classified as *nonoverridable* for a lower-priority user).
   - Made by the admin (`adminPerWorker`) on different temporary
     desktops with GPU `NVIDIA-T4-2Q`.
   - Each `booking_id` is stored in `testInfo.annotations` for
     cleanup.

### When

1. **As `user_e2e_01`** (role `user`, priority `500`): opens
   `/bookings/desktop/<user-desktop-id>` with GPU `NVIDIA-T4-2Q`.
2. `fetchEvents` queries the backend with `returnType=all`. The
   backend computes the plan and, for the window `[now+1h, now+2h]`,
   all 8 units are taken by *nonoverridable* bookings relative to the
   user's priority (`500 < 999`). The result of
   `compute_overridable_bookings` for that slot is
   `event_type = "unavailable"`.
3. `ReservablesPlannerProccess.get_item_availability` is called with
   `returnUnavailable = False` (default). It filters out the
   `unavailable` intervals before returning.

### Then

1. The response of `GET /api/v4/item/booking/get-desktop/<id>` does
   **not** contain any entry with `event_type = "available"` nor
   `"overridable"` for the window `[now+1h, now+2h]`. It does
   contain `available` strips for `[planStart, now+1h)` and `(now+2h,
   planEnd]`.
2. The Vue 2 calendar (`IsardCalendar.vue`) renders the
   *availability* column with two green strips separated by a gap
   (the cell's default background, not the `.available` class). The
   test asserts this by reading:
   - That `.event.available` elements in the *availability* split
     are **two** within the current week.
   - That the time slot `[now+1h, now+2h]` has **no** `.event.available`
     element over it.
3. The user can try to pick the "gap" slot:
   `BookingUtils.canCreate` returns `true` locally (no overlapping
   events from the frontend's perspective because the `unavailable`
   ones were not sent), but when pressing **Create** the backend
   responds `4xx` (no plan with enough units) and `$snotify` shows
   the error. No new booking is created.

### Observational case — admin (priority 999)

If the admin opens the same calendar, the same slot `[now+1h,
now+2h]` appears with `event_type = "overridable"` (orange) because
their priority would allow an override. **This** is the Scenario 3
case and must not be confused with the "gap" the `user`-role user
sees.

---

## Scenario 5 — *a user cannot create a booking with less advance time than the `forbid_time` of their priority*

Covers the `forbid_time` constraint of the effective priority rule.
This validation runs **client-side** in
`BookingUtils.priorityAllowed` (and on the calendar cell via
`priority.forbidTime`). The backend also validates it at
`POST /api/v4/item/booking/event`, but the UI never gets there.

### Given

1. The user `user_e2e_01` (role `user`) has a desktop with
   `reservables.vgpus = ["NVIDIA-T4-2Q"]` (seed with
   `priority_id = "test-booking-rule"`).
2. The rule `test-low-forbid-time` applies to the user with
   `forbid_time = 15` minutes. The call
   `GET /api/v4/items/bookings/get-priority-desktop/<id>` returns this
   value and `Booking.vue` stores it in the store
   (`priority.forbidTime = 15`).
3. The plan `test-t4-2q-available-plan` exists and covers `now → +N`.

### When

1. The user opens `/bookings/desktop/<id>`.
2. Picks a slot whose `start` is **inside** the `forbid_time` window.
   Cases to cover:
   - **Direct cell**: double-click + drag on a cell `start = now + 5
     min` (< 15 min). The `onCalendarCellClicked` handler calls
     `BookingUtils.priorityAllowed` and, since `checkForbidTime`
     returns `false`, **does not** open `#eventModal` — it shows the
     snotify `components.bookings.errors.forbid` directly.
   - **Modal**: if the user manages to open the modal over a valid
     cell and then manually edits `startDate` / `startTime` to land
     inside `forbid_time`, on pressing **Create** the same
     `priorityAllowed` function re-checks and fires the snotify
     inside `createEvent` (store `booking.js`).

### Then

1. The snotify `components.bookings.errors.forbid` appears.
2. **No** `POST /api/v4/item/booking/event` call is made (the test
   asserts this with a *response listener* on the endpoint).
3. The `#eventModal`, if it was open, stays open; no new event
   appears on the calendar.
4. If the user corrects `start` to `now + 16 min` (≥ 15 min) and
   presses **Create** again, the booking is created normally (success
   path of **S1**).

> For `admin` the effective rule is `default admins` with
> `forbid_time = 1` minute: the error path is barely observable
> (`start ≤ now` is already blocked by `EventModal.createEvent`
> before `forbid_time` is checked). That is why this scenario only
> makes sense with a user under a rule with `forbid_time` ≥ 5 min.

---

## Scenario 6 — *a user cannot create more bookings than the `max_items` of their priority*

Covers the `max_items` constraint. **This validation is not
client-side** (`BookingUtils.priorityAllowed` does not check it): the
only guard is on the backend through
`BookingsProcessed.get_total_user_bookings_count` (or equivalent inside
`create_booking_event`). The frontend only reacts to the `4xx` returned
by `POST /api/v4/item/booking/event` and surfaces the error via
`ErrorUtils.handleErrors`.

### Given

1. The user `user_e2e_01` (role `user`) has a desktop with
   `reservables.vgpus = ["NVIDIA-T4-2Q"]`.
2. The rule `test-low-forbid-time` applies with `max_items = 2`.
3. At setup, the test creates **2 future bookings** for this user on
   the same desktop in non-overlapping windows inside the plan
   `test-t4-2q-available-plan` (e.g. `[now+1h, now+1h30]` and
   `[now+2h, now+2h30]`) via `POST /api/v4/item/booking/event`
   authenticated as `user_e2e_01`. Both `booking_id` are stored in
   `testInfo.annotations` for cleanup.

### When

1. The user opens `/bookings/desktop/<id>` and tries to create a
   **third** booking in a window that is valid for the rest of their
   rules (`[now+3h, now+3h30]`, inside `max_time = 120 min` and
   outside `forbid_time = 15 min`).
2. The modal opens normally and, on pressing **Create**,
   `POST /api/v4/item/booking/event` fires.

### Then

1. The backend responds **4xx** (typically `412`/`428` or `409`
   depending on the implementation) with a `description` indicating
   `max_items` has been exceeded.
2. `ErrorUtils.handleErrors` shows the snotify corresponding to the
   returned code/description.
3. The modal stays open; no new event is added to the *bookings*
   split.
4. If the test queries
   `GET /api/v4/item/booking/get-desktop/<id>` again, only the 2
   setup bookings are there.
5. If the test deletes one of the existing bookings
   (`DELETE /api/v4/item/booking/event/<booking-id>`) and retries the
   third, the call now responds `< 400` and the booking is created
   correctly — confirming the limit depends on `max_items` and not on
   a permanent structural validation.

> The counter runs against **all** the user's future bookings (not
> only those for this desktop). If the user has bookings on other
> desktops, they count too. Tests must isolate this by using a clean
> `user_e2e_*` or by explicitly creating the 2 setup bookings to push
> the user to the limit just before the action.

---

## Scenario 7 — *a user cannot create bookings longer than the `max_time` of their priority*

Covers the `max_time` constraint (maximum duration in minutes of a
single booking). Like `forbid_time`, it is validated **client-side**
in `BookingUtils.priorityAllowed` (`checkMaxTime`) and also on the
backend.

### Given

1. The user `user_e2e_01` (role `user`) has a desktop with
   `reservables.vgpus = ["NVIDIA-T4-2Q"]`.
2. The rule `test-low-forbid-time` applies with `max_time = 120`
   minutes. `Booking.vue` stores it in the store
   (`priority.maxTime = 120`).
3. The plan `test-t4-2q-available-plan` exists.

### When

1. The user opens `/bookings/desktop/<id>`.
2. Picks a slot with `end - start > max_time`. Cases to cover:
   - **Cell + drag**: drags from `start = now + 30 min` to `end = now
     + 3 h` (= 150 min > 120). `BookingUtils.canCreate` /
     `priorityAllowed` returns `priorityAllowed = false` with error
     `components.bookings.errors.maximum-time`. The
     `onCalendarCellClicked` handler shows the snotify and refreshes
     the calendar to clear the temporary drag trace.
   - **Modal**: if the initial cell was valid but the user widens
     `endDate`/`endTime` inside the modal beyond 120 min, on pressing
     **Create** the same `priorityAllowed` function inside
     `createEvent` (store `booking.js`) re-checks and fires the
     snotify.

### Then

1. The snotify `components.bookings.errors.maximum-time` appears.
2. **No** `POST /api/v4/item/booking/event` is sent.
3. The calendar receives no new event (`refreshEvents` clears the
   drag placeholder).
4. If the user shortens `end` to `start + 120 min` (= 120, inclusive
   boundary because `checkMaxTime` compares `<= maxTime`), the
   booking is created correctly and `POST` responds `< 400`.

> The boundary is **inclusive** (`<= maxTime`). The test can add a
> sub-case `end - start = 120 min` to assert the success path right
> at the limit, and `end - start = 121 min` to assert the error path.

---

## Cleanup (afterEach)

Cleanup order is the inverse of creation, to avoid 4xx from
dependencies:

1. **Bookings** (`booking-id` in `testInfo.annotations`) →
   `DELETE /api/v4/item/booking/event/<id>`.
2. **Plans** created by the test (not from the seed) →
   `DELETE /api/v4/item/reservables-planner/<id>`. The seeds
   `test-t4-2q-available-plan` and `24ee2910-…` must **not** be
   touched.
3. **Desktops** created by the test →
   `DELETE /api/v4/item/desktop/<id>`.
4. **Priorities** created by the test → not applicable in this spec
   (the tests do not mutate `bookings_priority`).
5. Cleanup errors are swallowed so they don't mask the real cause of
   an earlier failure.

> No test in this spec must modify the `bookings_priority` rules of
> the seed, nor `reservables_vgpus`, nor the plans `24ee2910-…` /
> `test-t4-2q-available-plan`. If a scenario needs them in a
> different state, it must create its own desktop/booking/plan and
> clean it up in `afterEach`.

---

## Expected results — global summary

| Scenario | Expected coverage | Key checks |
| --- | --- | --- |
| S1 — Create booking on desktop with GPU + plan | ✅ | Driven through the modal; modal closes, no error toast, booking painted in the *bookings* split (`.vuecal__event.event` by title) |
| S2a — No plan for the `subitem_id` | ✅ | Calendar paints no `.available` strip; modal create → backend 4xx → `.snotify-error`; booking never painted |
| S2b — Desktop without GPU | ✅ | Calendar paints zero events; modal create blocked client-side → `.snotify-info` `errors.maximum-time`; no POST; modal stays open |
| S3a — Advanced (800) overrides `user` (300) | ✅ | `.overridable` strip on the advanced calendar; modal create → POST ok, modal closes, booking painted |
| S3b — `user` (300) cannot override advanced (800) | ✅ | No `.overridable` strip for the user; modal create → backend 4xx → `.snotify-error`, modal stays open, no booking painted, advanced booking intact |
| S3c — advanced (800) wider booking over a mid-window overridable | ✅ | Middle `.overridable` with `.available` margins; modal create of the wider window → POST ok, modal closes, booking painted |
| S4 — Gap on the calendar because all units are taken | ✅ | Feed has no `available`/`overridable` over the window; user calendar still paints `.available` strips and no `.overridable`; modal create on the gap → backend 4xx → `.snotify-error`, no booking painted |
| S4 — Admin view of the same range (sanity check) | ✅ | Slot appears as `overridable`, not as a gap |
| S5 — Booking inside `forbid_time` | ✅ | Driven through the modal; `.snotify-info` `errors.forbid`, no POST, modal stays open; correcting `start` reaches the success path (modal closes, booking painted) |
| S6 — Booking exceeding `max_items` | ✅ | Setup with 2 bookings at the limit; 3rd via modal → backend 4xx → `.snotify-error`, modal stays open, no booking painted; after deleting one, the modal retry succeeds and the booking is painted |
| S7 — Booking exceeding `max_time` | ✅ | Driven through the modal; `.snotify-info` `errors.maximum-time`, no POST, modal stays open; the `= max_time` boundary reaches the success path (modal closes, booking painted) |

---

## APIs touched by the flows (reference)

- `POST   /api/v4/item/desktop` — create the setup desktop with
  `reservables.vgpus`.
- `GET    /api/v4/item/booking/get-desktop/{id}?startDate=&endDate=&returnType=all`
  — calendar events (bookings + plans merged).
- `GET    /api/v4/items/bookings/get-priority-desktop/{id}` —
  effective priority for this desktop.
- `POST   /api/v4/item/booking/event` — create a booking
  `{item_id, item_type, title, start, end}`.
- `DELETE /api/v4/item/booking/event/{id}` — delete a booking
  (cleanup).
- `DELETE /api/v4/item/desktop/{id}` — delete a desktop (cleanup).
- `DELETE /api/v4/item/reservables-planner/{id}` — delete a plan
  (cleanup, only for plans created by the test).

---

## Relevant database state

- **`reservables_vgpus`**: the client filter
  (`get-allowed-reservables`) reads `allowed.{roles,categories,groups,users}`
  and compares against the session's identity. If a GPU has
  `allowed.roles = ["admin"]`, a `user`-role user does not see it in
  the dropdown even if it exists in the DB.
- **`resource_planner`**: each plan defines
  `(item_id, subitem_id, start, end, units, event_type="available")`.
  Without a plan covering the requested interval for a given
  `subitem_id`, no `available` strip is generated on the frontend
  (Case 2a).
- **`bookings`**: each booking has `plans[]` with `priority` (= the
  booker's effective priority at creation time). The `priority`
  comparison for override runs against **this** frozen value, not
  against the booker's current `bookings_priority.priority`.
- **`bookings_priority`**: the effective rule = first rule the user
  matches by (roles, categories, groups, users). If they match none,
  the `default` rule applies (priority `1`).

---

## Cases not covered (future)

- Concurrency: two users creating bookings on the same slot at the
  same moment (race between `compute_overridable_bookings` and
  `new_booking_plans`).
- Partial override: admin asks for more units than they can override
  with their priority (result: `overridable` strip but POST responds
  4xx with a conflict). Covered by apiv4 tests.
- Bookings on deployments with a GPU (role `advanced`).
- Inline editing of an existing booking (the modal code is commented
  out; only changeable via API).
- Real-time behaviour when SocketIO emits `bookings-update` during
  creation (minimal coverage in the current spec: the calendar only
  reacts via `add_booking`/`update_booking`/`remove_booking` but the
  spec only verifies the final state, not real-time propagation).
- Plans with a future `event_type` other than the current one (only
  `available` exists today).
