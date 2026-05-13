# Gestió de Bookables — Priority

Especificació funcional, llegible per humans, dels fluxos de la pantalla
**Bookables → Priority** de l'admin clàssic. Serveix de contracte per al
test E2E `tests/webapp/bookables/priority.spec.js`.

## Abast

- **Component**: webapp d'administració (admin "antic").
- **Pantalla**: **Bookables → Priority**
  (`/isard-admin/admin/domains/render/Priority`).
- **Taules cobertes**:
  - `#bookings_priority` — CRUD sobre regles de prioritat
    (taula RethinkDB `bookings_priority`).
  - `#bookings_priority_computed` — taula auxiliar **read-only** poblada
    explícitament en prémer **Compute** amb una `rule_id` seleccionada.
- **Accions cobertes**:
  - Llistar regles de prioritat.
  - **Crear** una regla nova (modal *Add new Priority resource* amb
    panell d'alloweds).
  - **Editar** una regla (modal *Edit Priority resource*).
  - **Eliminar** una regla (amb confirmació PNotify).
  - Gestionar **alloweds** d'una regla (modal compartit).
  - Expandir la fila i veure els alloweds en mode visor.
  - **Compute** users priorities per a una `rule_id` triada.
  - Verificar que les regles de **sistema** `default` i `default admins`
    només permeten l'acció *edit* (ni delete ni alloweds modal).
- **Fora d'abast**:
  - Aplicació de prioritats sobre bookings reals — exercitat
    indirectament a [`events.md`](events.md) i als tests d'apiv4.

## Rol i prerequisits comuns

| Element | Valor esperat |
| --- | --- |
| Rol | Administrador de la categoria `default` |
| Sessió | Iniciada a la webapp via fixture `login.js` |
| Seeds | `bookings_priority.json` proveeix les regles `default`, `default admins` i `test-low-forbid-time` (rule_id `test-booking-rule`) |
| Llistat | La taula `#bookings_priority` ha carregat i és visible |

## Dades comunes

| Camp | Valor d'exemple | Notes |
| --- | --- | --- |
| Nom | `e2e-prio-<worker>-<timestamp>` | 4–50 caràcters; mateix pattern que `gpus.md` |
| Descripció | `e2e priority rule created at <ISO timestamp>` | 0–255 caràcters |
| `rule_id` | `e2e-rule-<worker>-<timestamp>` | Identificador lliure, agrupador per famílies de regles |
| `priority` | `100` | Enter; el handler fa `parseInt` a `data2integers` |
| `forbid_time` | `30` | Enter, minuts |
| `max_time` | `120` | Enter, minuts |
| `max_items` | `3` | Enter |
| Alloweds | `{roles: ['user']}` | Test estable: rol `user`, sense categories/groups/users específics |

El `id` retornat per la creació es desa a
`testInfo.annotations` (`type: "priority-id"`) perquè el `afterEach` el
pugui eliminar encara que les assercions fallin. Per a regles del seed
mutades (Escenari 3), s'hi desa una còpia dels valors originals per
poder-los restaurar.

---

## Escenari 1 — *la pantalla llista les regles de prioritat existents*

### Donat (Given)

1. L'admin està autenticat i a la pantalla Bookables → Priority.

### Quan (When)

1. La pàgina carrega.

### Llavors (Then)

1. Es fa una crida `POST /api/v4/admin/table/bookings_priority` amb
   `{"order_by":"name"}`; respon amb estat `< 400` i un array de
   regles.
2. La taula `#bookings_priority` renderitza les files amb les columnes:
   *Rule*, *Name*, *Description*, *Roles*, *Category*, *Group*, *User*,
   *Priority*, *Forbid time*, *Max time*, *Max items*.
3. Les regles del seed (`default`, `default admins`,
   `test-low-forbid-time`) hi són amb els valors esperats.
4. Per a les files **del sistema** (`id ∈ {default, default admins}`),
   la columna d'accions només mostra el botó *edit*. Per a la resta de
   files es mostren *edit*, *alloweds* i *delete*.

També es fa una crida `GET /api/v4/items/bookings/priority-rules` per
poblar el dropdown del panell *Computed users priorities*.

---

## Escenari 2 — *l'admin crea una regla nova*

### Donat (Given)

1. L'admin està a la pantalla Priority.

### Quan (When)

1. Prem **Add new**.
2. S'obre el modal `#modalAddPriority`. El subpanell
   `#alloweds-priority-add` es prepara via `setAlloweds_add`.
3. Omple **Name**, **Description**, **Rule**, **Priority**,
   **Forbid time**, **Max time**, **Max items** amb valors vàlids
   (vegeu **Dades comunes**).
4. Activa el checkbox del rol `user` al panell d'alloweds i tria-hi
   l'opció `user`.
5. Prem **Create priority**.

### Llavors (Then)

1. La crida `POST /api/v4/admin/table/add/bookings_priority` rep el cos
   amb tots els camps convertits a enter on cal (`priority`,
   `forbid_time`, `max_time`, `max_items` són números, no strings) i
   amb la clau `allowed = {roles, categories, groups, users}`.
2. La resposta és `< 400` i conté l'`id` de la regla creada (desat a
   `testInfo.annotations`).
3. El modal es tanca; la taula es recarrega i la nova regla apareix
   ordenada per nom.

---

## Escenari 3 — *l'admin edita una regla*

### Donat (Given)

1. Existeix una regla d'usuari (creada per l'Escenari 2 o el seed
   `test-low-forbid-time`).

### Quan (When)

1. A la fila, prem la icona d'**editar**. S'obre `#modalEditPriority`
   amb tots els camps prefillats.
2. Modifica el nom i `max_items` (a `5`).
3. Prem **Update priority**.

### Llavors (Then)

1. La crida `PUT /api/v4/admin/table/update/bookings_priority` rep el
   cos amb `id` (= `priority_id` del formulari) i els camps numèrics
   convertits a enter. Respon amb estat `< 400`.
2. El modal es tanca; la taula es recarrega; la fila mostra els nous
   valors.

Si la regla és del sistema (`default` o `default admins`), el modal
**també** es pot obrir per editar però aquest escenari no muta les
files del sistema per no contaminar els altres tests del worker.

---

## Escenari 4 — *l'admin elimina una regla*

### Donat (Given)

1. Existeix una regla d'usuari (creada al setup del test, no del seed).

### Quan (When)

1. A la fila, prem la icona de **delete** (creu vermella).
2. Apareix un PNotify *Confirmation Needed* amb el text *Are you sure
   you want to delete: <name>?*.
3. Confirma.

### Llavors (Then)

1. Es fa una crida `DELETE /api/v4/item/booking/priority/<id>` que
   respon amb estat `< 400`.
2. La taula es recarrega i la fila desapareix.
3. Si es consulta de nou via
   `POST /api/v4/admin/table/bookings_priority`, la regla ja no hi és.

### Camí d'error

Si la regla està referenciada per algun *bookable* (`priority_id` a
`reservables_vgpus`), l'apiv4 ha de respondre 4xx i el handler mostra
un PNotify *ERROR deleting priority* amb el motiu retornat al
`description`. La taula **no** ha de perdre la fila.

> El test cobreix el camí d'èxit creant una regla pròpia. La branca
> *referenciada* es deixa per a un escenari complementari quan
> [`resources.md`](resources.md) tingui mecanisme estable per fer-hi
> apuntar i restablir-hi un bookable temporalment.

---

## Escenari 5 — *les regles del sistema no es poden eliminar*

### Donat (Given)

1. Les regles `default` i `default admins` (seed) són visibles a la
   taula.

### Quan (When)

1. L'admin inspecciona les seves accions a la columna final.

### Llavors (Then)

1. Per a `id ∈ {default, default admins}`, només es renderitza el botó
   d'**edit**: la columna **no** conté `#btn-delete` ni `#btn-alloweds`
   (`columnDefs[targets:12]` ho controla a `bookables_priority.js`).
2. Cap test pot disparar
   `DELETE /api/v4/item/booking/priority/default` des d'aquesta UI.

---

## Escenari 6 — *l'admin gestiona els alloweds d'una regla*

### Donat (Given)

1. Existeix una regla d'usuari amb alloweds prèviament definits
   (`{roles: ['user']}`).

### Quan (When)

1. A la fila, prem la icona d'**alloweds**. S'obre `#modalAlloweds` amb
   títol *Edit "<name>" permissions*.
2. La crida `POST /api/v4/allowed/table/bookings_priority` retorna els
   alloweds actuals; els checkboxes i `select2` es prefills correctament.
3. Modifica les seleccions (per exemple, afegeix el rol `advanced`).
4. Prem **Update permissions**.

### Llavors (Then)

1. La crida `POST /api/v4/admin/allowed/update/bookings_priority` rep
   el cos amb `id`, `table` i `allowed = {roles, categories, groups,
   users}`. Respon amb estat `< 400`.
2. Apareix una notificació PNotify *Alloweds updated successfully*.
3. El modal es tanca.
4. Si es torna a obrir el modal, els checkboxes reflecteixen el nou
   estat.

---

## Escenari 7 — *l'admin expandeix la fila i veu els alloweds en mode visor*

### Donat (Given)

1. Existeix una regla amb alloweds definits.

### Quan (When)

1. A la fila, prem el botó **+** (`td.details-control`).
2. La fila expandeix i renderitza `bookables_priority_detail.html`,
   que conté `alloweds-<id>` dins.
3. La pàgina crida `setAlloweds_viewer('#alloweds-<id>', <id>,
   "bookings_priority")`, que fa
   `POST /api/v4/allowed/table/bookings_priority` amb `{id}`.

### Llavors (Then)

1. La crida respon amb estat `< 400`.
2. El panell expandit llista els alloweds en format read-only,
   coherent amb els valors mostrats al modal de l'Escenari 6.

---

## Escenari 8 — *validació de camps obligatoris i tipus*

### Donat (Given)

1. L'admin està al modal `#modalAddPriority`.

### Quan (When)

1. Casos a cobrir, un per un:
   - **Nom invàlid**: < 4 caràcters, o fora del pattern (per ex.
     `prio@1`).
   - **Camps numèrics obligatoris buits**: `priority`, `forbid_time`,
     `max_time` o `max_items`.
   - **Valor no numèric** a un dels camps `type="number"`.
2. Prem **Create priority**.

### Llavors (Then)

1. Parsley bloqueja l'enviament (`form.parsley().isValid()` és
   `false`).
2. **No** es fa cap crida a
   `POST /api/v4/admin/table/add/bookings_priority`.
3. El modal roman obert i conserva la resta de dades.

---

## Escenari 9 — *l'admin intenta crear una regla duplicada*

### Donat (Given)

1. Existeix una regla amb un `name` determinat (el creat a l'Escenari
   2 o una regla del seed).

### Quan (When)

1. L'admin obre el modal *Add new* i hi introdueix **el mateix `name`**
   (i les altres dades vàlides).
2. Prem **Create priority**.

### Llavors (Then)

1. L'API respon amb estat `409`.
2. El handler mostra un PNotify *ERROR creating priority* amb el text
   de `xhr.responseJSON.description`.
3. El modal roman obert; no s'afegeix cap fila nova a la taula.

---

## Escenari 10 — *l'admin computa les prioritats d'una regla*

### Donat (Given)

1. Existeix la regla `test-booking-rule` (seed `test-low-forbid-time`)
   que aplica al rol `user`.
2. El dropdown del panell *Computed users priorities* ha estat poblat
   per la crida inicial `GET /api/v4/items/bookings/priority-rules`.

### Quan (When)

1. Al dropdown, selecciona `test-booking-rule`.
2. Prem **Compute**.
3. Apareix un PNotify *Compute users priorities* amb avís de cost; ho
   confirma.

### Llavors (Then)

1. Es fa una crida `POST /api/v4/items/bookings/priorities` amb
   `{"rule_id":"test-booking-rule"}`. Respon amb estat `< 400`.
2. La taula `#bookings_priority_computed` es buida i es repobla amb
   els usuaris retornats (mínim: `user01` del seed, rol `user`).
3. Cancel·lar el PNotify abans de confirmar **no** dispara la crida.

---

## Neteja (afterEach)

1. Es recupera l'`id` de la regla creada per aquest test des de
   `testInfo.annotations`.
2. Si existeix, s'elimina via
   `DELETE /api/v4/item/booking/priority/<id>`.
3. Si el test ha modificat una regla del seed, es restauren els seus
   camps via `PUT /api/v4/admin/table/update/bookings_priority`.
4. Si el test ha modificat els alloweds d'una regla del seed, es
   restauren via `POST /api/v4/admin/allowed/update/bookings_priority`.
5. Els errors de neteja es silencien.

---

## Resultats esperats — resum global

| Escenari | Cobertura prevista | Comprovacions clau |
| --- | --- | --- |
| S1 — Llistar regles | ✅ | POST `bookings_priority` ok; seeds presents; botons d'acció condicionats per `id ∈ {default, default admins}` |
| S2 — Crear regla | ✅ | Modal poblat; POST `add/bookings_priority` ok amb camps com a enter; taula refrescada |
| S3 — Editar regla | ✅ | Modal prefillat; PUT `update/bookings_priority` ok; valors actualitzats |
| S4 — Eliminar regla (èxit) | ✅ | PNotify confirm; DELETE `/booking/priority/{id}` ok; fila desapareix |
| S4b — Eliminar referenciada | ⏭ `skip` | Requereix bookable que apunti a la regla; deixat per a iteració amb `resources.md` |
| S5 — Regles del sistema no eliminables | ✅ | UI: ni `btn-delete` ni `btn-alloweds` renderitzats per a `default` i `default admins` |
| S6 — Alloweds modal | ✅ | POST `allowed/table` prefills; POST `allowed/update` aplica canvis |
| S7 — Alloweds viewer al detall | ✅ | Fila expandida, llistat read-only via `setAlloweds_viewer` |
| S8 — Validació | ✅ | Parsley bloqueja `Send`; cap POST |
| S9 — Duplicat | ✅ | API respon 409; PNotify d'error; cap fila nova |
| S10 — Compute users priorities | ✅ | PNotify confirm; POST `bookings/priorities` ok; taula computada poblada |

## API tocades pels fluxos (referència)

- `POST   /api/v4/admin/table/bookings_priority` — datatable load.
- `POST   /api/v4/admin/table/add/bookings_priority` — crear regla.
- `PUT    /api/v4/admin/table/update/bookings_priority` — actualitzar
  regla.
- `DELETE /api/v4/item/booking/priority/{id}` — eliminar regla.
- `GET    /api/v4/items/bookings/priority-rules` — poblar dropdown
  *Computed users priorities*.
- `POST   /api/v4/items/bookings/priorities` — computar usuaris per a
  una `rule_id`. Body `{rule_id}`.
- `POST   /api/v4/allowed/table/bookings_priority` — llegir alloweds.
- `POST   /api/v4/admin/allowed/update/bookings_priority` —
  actualitzar alloweds.
- `POST   /api/v4/admin/allowed/term/{roles|categories|groups|users}`
  — termes per al `select2` del panell d'alloweds.

## Estat de base de dades rellevant

- Taula `bookings_priority`: una fila per regla. Les files `id`
  `default` i `default admins` són del sistema i protegides
  client-side.
- `reservables_vgpus.priority_id` apunta opcionalment a una regla via
  el seu `rule_id` (no l'`id` — confús: vegeu `bookables_priority.js`
  on `data.priority_id` referencia el `rule_id`).

## Casos no coberts (futurs)

- Eliminació d'una regla amb dependències (Escenari 4b).
- Validació backend que `forbid_time < max_time` i altres invariants
  de negoci.
- Concurrència: dos admins editant la mateixa regla.
- Test del flux *Compute* contra un dataset gran amb molts usuaris
  (rendiment).
