# Gestió de Bookables — Events

Especificació funcional, llegible per humans, dels fluxos de la pantalla
**Bookables → Events** de l'admin clàssic. Serveix de contracte per al
test E2E `tests/webapp/bookables/events.spec.js`.

## Abast

- **Component**: webapp d'administració (admin "antic").
- **Pantalla**: **Bookables → Events**
  (`/isard-admin/admin/domains/render/BookablesEvents`).
- **Taules cobertes**:
  - `#table-planning` — plans de disponibilitat
    (`resource_planner` a RethinkDB).
  - `#table-booking` — bookings (`bookings` a RethinkDB).
  - `#table-booking-scheduler` — jobs del scheduler de bookings
    (read-only).
- **Accions cobertes**:
  - Llistar plans, bookings i scheduler jobs.
  - Filtrar plans i bookings per **rang de dates** (filtre clientside
    via `$.fn.dataTable.ext.search`).
  - Expandir un plan i veure'n els bookings inclosos
    (`#table-p-detail`).
  - Expandir un booking i veure els plans que el contenen
    (`#table-b-detail`).
  - **Buidar** un plan (treure'n tots els bookings).
  - **Eliminar** un plan.
  - **Eliminar** un booking individual (des de la taula principal o
    des de la subtaula d'un plan).
  - Cross-link entre files: prémer una fila del detall filtra l'altra
    taula principal.
- **Fora d'abast**:
  - Creació de plans i bookings — es generen via les pantalles
    d'usuari (Bookings i Plans del frontend Vue 3) i mitjançant el
    scheduler; cobert per [`../../tests/webapp/vue3-bookings.spec.js`](../../tests/webapp/vue3-bookings.spec.js)
    i `vue3-planning.spec.js`.
  - Edició de bookings — disponible només via l'endpoint
    `/item/booking/event/{id}/edit`, no des d'aquesta pantalla.
  - SocketIO realtime updates — `bookables_events.js` carrega
    `socketio.js` però aquest spec no exercita esdeveniments en viu.

## Rol i prerequisits comuns

| Element | Valor esperat |
| --- | --- |
| Rol | Administrador de la categoria `default` |
| Sessió | Iniciada a la webapp via fixture `login.js` |
| Seeds | `resource_planner.json` (plans `24ee2910-…` i `test-t4-2q-available-plan`) + `bookings.json` (dos bookings d'admin lligats a `NVIDIA-A16-2Q` dins el plan `24ee2910-…`) |
| Llistat | Les tres taules han carregat |

## Dades comunes

| Camp | Valor d'exemple | Notes |
| --- | --- | --- |
| Plan target | `test-t4-2q-available-plan` | Plan del seed sense bookings; segur d'eliminar/buidar |
| Booking target | Booking creat al setup del test via API | Garantit que el test no toca els bookings d'altres workers |
| Format de data | `DD-MM-YYYY HH:mm` | El filtre `daterangepicker` el fa servir; el render de columnes usa `DD-MM-YY HH:mm` |
| `start-min` per defecte | `moment().format("DD-MM-YYYY HH:mm")` | El JS l'aplica a l'init de la pàgina |

Els tests que muten un plan o un booking del seed han de **crear-ne
una còpia** abans i operar sobre la còpia. Els seeds són compartits
entre workers.

---

## Escenari 1 — *la pantalla llista plans, bookings i scheduler jobs*

### Donat (Given)

1. L'admin està autenticat i a la pantalla Bookables → Events.

### Quan (When)

1. La pàgina carrega.

### Llavors (Then)

1. Es fan tres crides en paral·lel:
   - `GET /api/v4/items/reservables-planner` per a `#table-planning`.
   - `GET /api/v4/items/bookings/all` per a `#table-booking`.
   - `GET /api/v4/admin/items/scheduler/jobs/bookings` per a
     `#table-booking-scheduler`.
2. Totes tres responen amb estat `< 400`.
3. `#table-planning` mostra els plans del seed (`24ee2910-…`,
   `test-t4-2q-available-plan`) i els que el scheduler hagi pogut
   crear. Cada fila renderitza els botons **Empty** i **Delete plan**.
4. `#table-booking` mostra els bookings del seed (`0a1b2c3d-…` i
   `1b2c3d4e-…`, tots dos de l'admin). Cada fila té un botó
   **Delete booking**.
5. `#table-booking-scheduler` mostra els jobs del scheduler (nom, tipus,
   *Next run*, *kwargs*). El nombre de files depèn de la configuració;
   l'spec només verifica que la taula carrega sense error i que
   *Next run* es renderitza amb `moment.unix(...)`.

> **Nota**: per defecte el filtre `start-min` s'inicialitza a la data
> actual, així que plans i bookings passats no apareixen fins que
> l'admin esborri el filtre.

---

## Escenari 2 — *l'admin filtra plans per rang de dates*

### Donat (Given)

1. `#table-planning` mostra plans amb dates conegudes (seed:
   `start.epoch_time = 1000000000` ≈ 2001, `end.epoch_time =
   10000000000` ≈ 2286).

### Quan (When)

1. A `#table-planning-filters #start-min`, introdueix una data
   posterior a tots els plans del seed (per exemple
   `01-01-2300 00:00`).
2. Aplica el filtre (`apply.daterangepicker`).

### Llavors (Then)

1. La funció `filterDateDatatable("table-planning")` aplica un filtre
   clientside que amaga totes les files: el rang `[01-01-2300 …]` no
   intersecciona cap interval `start–end` del seed.
2. La taula mostra el seu missatge per defecte *No matching records
   found*.

### Camí complementari

Si l'admin prem la icona **×** al costat del camp (`.clear-date`), el
valor del camp es buida i la taula torna a mostrar totes les files.

---

## Escenari 3 — *l'admin filtra bookings per rang de dates*

Anàleg a l'Escenari 2 sobre `#table-booking`, amb la diferència que
l'objecte d'`apply.daterangepicker` apunta a `table-booking` i el
filtre s'aplica sobre les columnes `[1]` (start) i `[2]` (end) dels
bookings.

---

## Escenari 4 — *l'admin expandeix un plan i veu els bookings que conté*

### Donat (Given)

1. Existeix el plan `24ee2910-c0e5-44bd-9a2b-5603ddc65d57` amb dos
   bookings al seed.

### Quan (When)

1. A la fila del plan, prem el botó **+** (`td.details-control`).
2. El JS clona `#planning-detail` i crida
   `renderPlanningDetailDatatable(planId)`, que crea
   `#table-p-detail` amb font
   `GET /api/v4/item/reservables-planner/{planId}/bookings`.

### Llavors (Then)

1. La crida respon amb estat `< 400` i la subtaula mostra dues files
   (els dos bookings de l'admin del seed).
2. Cada fila té el botó **Delete booking**.
3. La subtaula també està protegida pel filtre `daterangepicker`.
4. Prémer la mateixa fila del plan una segona vegada la replega
   (`row.child.hide`).
5. Si una altra fila ja era oberta, primer es tanca abans d'obrir la
   nova (`bookables_events.js` ho garanteix amb `if
   (planning_table.row('.shown').length)`).

---

## Escenari 5 — *l'admin expandeix un booking i veu els plans que el contenen*

### Donat (Given)

1. Existeix el booking `0a1b2c3d-…` (seed) amb un plan associat
   (`24ee2910-…`).

### Quan (When)

1. A la fila del booking, prem el botó **+**.
2. El JS clona `#booking-detail` i crida
   `renderBookingDetailDatatable(bookingId)`, que crea
   `#table-b-detail` amb font
   `GET /api/v4/item/booking/{bookingId}/plans`.

### Llavors (Then)

1. La crida respon amb estat `< 400` i la subtaula mostra el plan
   `24ee2910-…`.
2. La subtaula no té botons d'acció (només informatius).

---

## Escenari 6 — *l'admin buida un plan*

### Donat (Given)

1. Existeix un plan creat pel test (còpia del seed o nou) que conté
   almenys un booking.

### Quan (When)

1. A la fila del plan, prem **Empty**.
2. Apareix un PNotify *Empty plan — Are you sure you want to clear all
   the bookings in this plan?*. Confirma.

### Llavors (Then)

1. Es fa una crida `DELETE /api/v4/item/booking/empty/{planId}` que
   respon amb estat `< 400`.
2. Apareix un PNotify d'èxit *Deleted — Plan emptied successfully*.
3. `#table-planning` es recarrega; la columna *Bookings* del plan
   passa a `0`.
4. Si es consulta
   `GET /api/v4/item/reservables-planner/{planId}/bookings`, retorna
   una llista buida.

### Camí d'error

Si l'API respon 4xx/5xx, el handler mostra un PNotify
*ERROR emptying plan* amb `responseJSON.description` o un fallback
*Something went wrong*. La taula **no** ha de perdre la fila.

### Cancel·lació

Si l'admin no confirma el PNotify, **no** es fa cap crida `DELETE`.

---

## Escenari 7 — *l'admin elimina un plan*

### Donat (Given)

1. Existeix un plan creat pel test (per exemple `test-t4-2q-available-plan`
   o una còpia, no compartit amb cap altre worker).

### Quan (When)

1. A la fila del plan, prem **Delete**.
2. PNotify *Delete plan — Are you sure?*. Confirma.

### Llavors (Then)

1. Es fa una crida
   `DELETE /api/v4/item/reservables-planner/{planId}` que respon amb
   estat `< 400`.
2. Apareix un PNotify d'èxit *Deleted — Plan deleted successfully*.
3. `#table-planning` es recarrega i la fila desapareix.
4. Si el plan tenia bookings que el referenciaven exclusivament, el
   handler del backend els neteja segons la lògica de
   `ReservablesPlannerProccess.delete_item` — comprovació delegada
   als tests unitaris d'apiv4.

### Camí d'error i cancel·lació

Idèntics a l'Escenari 6 (PNotify d'error o cancel sense crida).

---

## Escenari 8 — *l'admin elimina un booking des de la taula principal*

### Donat (Given)

1. Existeix un booking creat pel test via API
   (`POST /api/v4/item/booking/event`) per aïllament entre workers.

### Quan (When)

1. A la fila del booking dins `#table-booking`, prem **Delete**.
2. PNotify *Delete booking — Are you sure?*. Confirma.

### Llavors (Then)

1. Es fa una crida `DELETE /api/v4/item/booking/event/{bookingId}` que
   respon amb estat `< 400`.
2. Apareix un PNotify d'èxit *Deleted — Booking deleted successfully*.
3. `#table-booking` es recarrega; la fila desapareix.

### Cas d'error rellevant

Si el booking està **in-progress** (desktop o deployment encara en
execució), apiv4 respon `428` i el handler mostra un PNotify d'error.
Aquest cas és difícil de muntar de manera estable des d'aquesta
pantalla — queda **`test.skip`** i cobert pels tests d'apiv4
(`test_bookings.py`).

---

## Escenari 9 — *l'admin elimina un booking des de la subtaula d'un plan*

Variant de l'Escenari 8 a través del *path* del detall del plan
(`#table-p-detail`). En prémer **Delete** dins la subtaula:

1. Es dispara la mateixa crida
   `DELETE /api/v4/item/booking/event/{bookingId}`.
2. En èxit, **`booking_table.ajax.reload()`** es crida — la taula
   principal de bookings es refresca tot i que la interacció hagi
   estat a la subtaula.
3. **`p_detail_table.ajax.reload(null, false)`** també es crida — la
   fila esborrada desapareix de la subtaula sense haver de plegar i
   tornar a obrir el detall del plan.

---

## Escenari 10 — *cross-link de la subtaula a la taula principal*

### Donat (Given)

1. Un plan està expandit a `#table-planning` i mostra els seus bookings
   a `#table-p-detail`.

### Quan (When)

1. L'admin clica una `<td>` (no botó) d'una fila de
   `#table-p-detail`.

### Llavors (Then)

1. El handler captura l'`id` del booking, omple
   `#table-booking_filter input` amb aquest valor, fa scroll fins a
   `#booking-panel` i dispara `input` perquè DataTables filtri.
2. La taula `#table-booking` queda filtrada per aquest booking.

I la simètrica: clicar una `<td>` de `#table-b-detail` (subtaula d'un
booking) filtra `#table-planning` pel `plan_id` corresponent.

---

## Escenari 11 — *cancel·lar les confirmacions de delete/empty no fa res*

> Casos extreta de la triple ramificació *cancel* del handler de
> botons (planning empty / planning delete / booking delete).

### Donat (Given)

1. Existeix un plan creat pel test amb bookings.

### Quan (When)

1. Prem **Empty** o **Delete** a `#table-planning`, o **Delete** a
   `#table-booking`. Quan apareix el PNotify, **no** confirma (no
   clica *OK* o tanca el toast).

### Llavors (Then)

1. **No** es fa cap crida `DELETE /api/v4/...`.
2. L'estat de les taules no canvia.

---

## Neteja (afterEach)

1. Es recuperen els `id`s creats pel test des de
   `testInfo.annotations` (tipus `booking-id`, `plan-id`).
2. Bookings creats pel test que encara existeixin s'eliminen via
   `DELETE /api/v4/item/booking/event/{id}`.
3. Plans creats pel test que encara existeixin s'eliminen via
   `DELETE /api/v4/item/reservables-planner/{id}`.
4. Plans del seed que el test hagi mutat indirectament (cas extrem,
   no previst per cap escenari d'aquest spec) **no** es restauren des
   d'aquí: el test ha de fer setup/teardown propi.
5. Els errors de neteja es silencien.

---

## Resultats esperats — resum global

| Escenari | Cobertura prevista | Comprovacions clau |
| --- | --- | --- |
| S1 — Llistar plans / bookings / scheduler | ✅ | Les tres GET responen ok; seeds presents; columnes renderitzades amb `moment` |
| S2 — Filtrar plans per data | ✅ | Filtre clientside oculta files; `.clear-date` les recupera |
| S3 — Filtrar bookings per data | ✅ | Idèntic a S2 sobre `#table-booking` |
| S4 — Detall del plan (bookings inclosos) | ✅ | GET `/reservables-planner/{id}/bookings` ok; subtaula amb files esperades |
| S5 — Detall del booking (plans contenidors) | ✅ | GET `/booking/{id}/plans` ok; subtaula amb el plan associat |
| S6 — Empty plan | ✅ | PNotify confirm; DELETE `/booking/empty/{id}` ok; *Bookings = 0* |
| S7 — Delete plan | ✅ | PNotify confirm; DELETE `/reservables-planner/{id}` ok; fila desapareix |
| S8 — Delete booking (taula principal) | ✅ | Test crea booking via API en finestra futura del seu propi plan, PNotify confirm, DELETE `/booking/event/{id}` ok, fila desapareix |
| S8b — Delete booking in-progress | ⏭ `skip` | Requereix desktop en execució lligat al booking |
| S9 — Delete booking (subtaula del plan) | ✅ | Mateixa crida; taula principal de bookings es refresca |
| S10 — Cross-link entre taules | ✅ | Click a `<td>` filtra l'altra taula i fa scroll |
| S11 — Cancel·lar PNotify no fa res | ✅ | Cap DELETE; estat preservat |

## API tocades pels fluxos (referència)

- `GET    /api/v4/items/reservables-planner` — llista de plans.
- `GET    /api/v4/items/bookings/all` — llista de bookings (admin).
- `GET    /api/v4/admin/items/scheduler/jobs/bookings` — jobs del scheduler.
- `GET    /api/v4/item/reservables-planner/{planId}/bookings` —
  bookings dins d'un plan.
- `GET    /api/v4/item/booking/{bookingId}/plans` — plans que
  contenen un booking.
- `DELETE /api/v4/item/booking/empty/{planId}` — buidar un plan
  (treure tots els bookings).
- `DELETE /api/v4/item/reservables-planner/{planId}` — eliminar un
  plan.
- `DELETE /api/v4/item/booking/event/{bookingId}` — eliminar un
  booking.

> Per a la **creació** de bookings/plans necessària per al *setup*
> dels tests, els helpers han d'usar `POST /api/v4/item/booking/event`
> i `POST /api/v4/item/reservables-planner` (no exposats des d'aquesta
> pantalla).

## Estat de base de dades rellevant

- Taula `resource_planner`: una fila per plan (interval temporal
  `start–end` sobre un `subitem_id`, p. ex. `NVIDIA-A16-2Q`).
- Taula `bookings`: una fila per booking, amb `plans[]` que llista els
  plans que el contenen.
- L'eliminació d'un plan **no** elimina automàticament els seus
  bookings: el handler d'apiv4
  (`ReservablesPlannerProccess.delete_item`) reorganitza les
  referències segons la seva lògica.

## Casos no coberts (futurs)

- Eliminar un booking que estigui *in-progress* (resposta 428).
- Comportament en temps real quan SocketIO emet `bookings-update` (el
  test actual desestima la càrrega de `socketio.js`).
- Edició inline de bookings (no exposada per aquesta pantalla; viu a
  les pantalles d'usuari Vue 3).
- Plans amb `event_type ≠ "available"` (no representats al seed).
- Filtre `daterangepicker` amb només `end-max` definit (cas
  específic dins `filterDateDatatable`).
