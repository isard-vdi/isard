# Gestió de Bookables — Resources

Especificació funcional, llegible per humans, dels fluxos de la pantalla
**Bookables → Resources** de l'admin clàssic. Serveix de contracte per al
test E2E `tests/webapp/bookables/resources.spec.js`.

## Abast

- **Component**: webapp d'administració (admin "antic").
- **Pantalla**: **Bookables → Resources**
  (`/isard-admin/admin/domains/render/Bookables`).
- **Taula coberta**: `#reservables_vgpus` — llistat de *bookables*
  vGPU del sistema (un per perfil de GPU habilitat almenys en una GPU).
- **Accions cobertes**:
  - Llistar els *bookables* vGPU existents.
  - Editar el **nom**, la **descripció** i la **regla de prioritat**
    (`priority_id`) d'un *bookable*.
  - Gestionar els **alloweds** (permissos) del *bookable* mitjançant el
    modal compartit (`modalAllowedsFormShow`).
  - Expandir la fila i veure els alloweds en mode visor (read-only).
- **Fora d'abast**:
  - Creació i eliminació d'entrades a `reservables_vgpus`: són efectes
    laterals d'habilitar/inhabilitar perfils a **Hypervisors → GPUs**
    i estan cobertes a [`../gpus.md`](../gpus.md) (Escenaris 5, 6 i 13).
  - Edició de la regla de prioritat en si — coberta a
    [`priority.md`](priority.md).
  - Visualització de plans i bookings — coberta a
    [`events.md`](events.md).

## Rol i prerequisits comuns

| Element | Valor esperat |
| --- | --- |
| Rol | Administrador de la categoria `default` |
| Sessió | Iniciada a la webapp via fixture `login.js` |
| Infraestructura | Almenys un *bookable* vGPU al sistema (seed `reservables_vgpus.json` proveeix `NVIDIA-A16-2Q`, `NVIDIA-A16-4Q`, `NVIDIA-T4-2Q`) |
| Regles de prioritat | Almenys una regla seleccionable al dropdown del modal d'edició (seed proveeix `default` i `test-booking-rule`) |
| Llistat | La taula `#reservables_vgpus` ha carregat i és visible |

## Dades comunes

| Camp | Valor d'exemple | Notes |
| --- | --- | --- |
| Nom | `e2e-vgpu-<worker>-<timestamp>` | 4–50 caràcters; pattern `^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$` |
| Descripció | `e2e vGPU bookable updated at <ISO timestamp>` | 0–255 caràcters |
| Prioritat | `default` o `test-booking-rule` | Triada del dropdown poblat per `/api/v4/items/bookings/priority-rules` |
| Bookable target | `NVIDIA-T4-2Q` | *Bookable* del seed que no és utilitzat per cap booking del sistema; segur de mutar |

El nom (original) del *bookable* es desa a `testInfo.annotations`
(`type: "vgpu-bookable-original-name"`) perquè el `afterEach` pugui
restaurar-lo encara que les assercions fallin.

---

## Escenari 1 — *la pantalla llista els bookables vGPU existents*

### Donat (Given)

1. L'admin està autenticat i a la pantalla Bookables → Resources.

### Quan (When)

1. La pàgina carrega.

### Llavors (Then)

1. Es fa una crida `POST /api/v4/admin/table/reservables_vgpus` amb
   `{"order_by":"name"}`; respon amb estat `< 400` i un array de
   *bookables*.
2. La taula `#reservables_vgpus` renderitza una fila per cada element,
   amb columnes: nom, descripció, *Priority Rule*, marca, model,
   perfil, unitats, *total units*.
3. Els seeds `NVIDIA-A16-2Q`, `NVIDIA-A16-4Q` i `NVIDIA-T4-2Q` apareixen
   a la taula amb els valors esperats (vegeu `reservables_vgpus.json`).
4. La fila sentinella `None` (sense `priority_id`) renderitza `-` a la
   columna *Priority Rule*.

---

## Escenari 2 — *l'admin edita el nom i la descripció d'un bookable*

### Donat (Given)

1. Existeix el *bookable* `NVIDIA-T4-2Q` a la taula (seed) i no és
   utilitzat per cap booking del sistema.
2. S'ha desat el nom original a `testInfo.annotations`.

### Quan (When)

1. A la fila, prem la icona d'**editar** (llapis).
2. S'obre el modal `#modalEditBookable` amb el nom i la descripció
   prefillats.
3. Mentre el modal s'obre, es fa una crida
   `GET /api/v4/items/bookings/priority-rules` per poblar el dropdown
   **Priority**; el valor actual `test-booking-rule` queda seleccionat.
4. Canvia el nom a `e2e-vgpu-<worker>-<timestamp>` i la descripció a
   un text nou. Manté el `priority_id` actual.
5. Confirma els canvis amb **Update vGPU**.

### Llavors (Then)

1. El sistema envia
   `PUT /api/v4/admin/table/update/reservables_vgpus` amb el cos
   `{id, name, description, priority_id}`. Respon amb estat `< 400`.
2. El modal es tanca, la taula es recarrega i la fila mostra el nou
   nom i la nova descripció.
3. Si es consulta de nou via
   `POST /api/v4/admin/table/reservables_vgpus`, retorna els valors
   actualitzats.

---

## Escenari 3 — *l'admin canvia la regla de prioritat d'un bookable*

### Donat (Given)

1. Existeix `NVIDIA-T4-2Q` amb `priority_id = "test-booking-rule"`.

### Quan (When)

1. Obre el modal d'edició.
2. Al dropdown **Priority**, tria `default`.
3. Prem **Update vGPU**.

### Llavors (Then)

1. `PUT /api/v4/admin/table/update/reservables_vgpus` rep
   `priority_id: "default"`.
2. La taula refresca la columna *Priority Rule* del *bookable* a
   `default`.
3. La taula computada de **Priority → Computed users priorities** no
   queda afectada (només es regenera explícitament des d'allà).

---

## Escenari 4 — *l'admin gestiona els alloweds d'un bookable*

### Donat (Given)

1. Existeix un *bookable* a la taula.

### Quan (When)

1. A la fila, prem la icona d'**alloweds** (icona d'usuaris blava).
2. S'obre el modal `#modalAlloweds` titulat *Edit "<nom>" permissions*.
3. Es fa una crida `POST /api/v4/allowed/table/reservables_vgpus` amb
   `{id}`; els checkboxes de **roles / categories / groups / users** es
   marquen amb els valors actuals.
4. El modal mostra l'avís específic d'`alloweds_panel` per a
   `reservables_vgpus` (la llista de taules incloses dins
   `modalAllowedsFormShow` el porta).
5. Modifica les seleccions (per ex. afegeix el rol `user`).
6. Prem **Update permissions**.

### Llavors (Then)

1. `POST /api/v4/admin/allowed/update/reservables_vgpus` rep el cos
   amb `id`, `table` i la nova estructura `allowed = {roles, categories,
   groups, users}`. Respon amb estat `< 400`.
2. Apareix una notificació PNotify d'èxit *Alloweds updated
   successfully*.
3. El modal es tanca.
4. Si es torna a obrir el modal, els checkboxes reflecteixen el nou
   estat.

---

## Escenari 5 — *l'admin expandeix la fila i veu els alloweds en mode visor*

### Donat (Given)

1. Existeix un *bookable* amb alloweds definits (per exemple
   `NVIDIA-A16-2Q`, rol `admin`).

### Quan (When)

1. A la fila, prem el botó **+** (`td.details-control`).
2. La fila s'expandeix i renderitza `bookables_detail.html`, que conté
   `alloweds-<id>` dins.
3. La pàgina crida `setAlloweds_viewer('#alloweds-<id>', <id>,
   "reservables_vgpus")`, que fa
   `POST /api/v4/allowed/table/reservables_vgpus` amb `{id}`.

### Llavors (Then)

1. La crida respon amb estat `< 400`.
2. El panell expandit llista els alloweds en format read-only (taula
   `table-alloweds-<id>` amb files per a roles, categories, groups,
   users). Si tots els valors són arrays buits, mostra una fila única
   *Everyone — Has access*.
3. Prémer el botó de la mateixa fila una segona vegada la replega.

---

## Escenari 6 — *l'admin intenta desar amb un nom invàlid*

### Donat (Given)

1. L'admin està al modal `#modalEditBookable` amb el dropdown de
   prioritat carregat.

### Quan (When)

1. Introdueix al camp **Name** un valor invàlid. Casos a cobrir:
   - Massa curt (< 4 caràcters), p. ex. `abc`.
   - Fora del joc permès, p. ex. `vgpu@1`, `my/vgpu`.
   - Buit.
2. Prem **Update vGPU**.

### Llavors (Then)

1. La validació de client (Parsley) bloqueja l'enviament i marca el
   camp amb classe `parsley-error`.
2. **No** es fa cap crida a `/api/v4/admin/table/update/...`.
3. El modal roman obert.

> Igual que a la pantalla GPUs, la branca *massa llarg* no es pot
> exercitar via `fill()` perquè `<input>` té `maxlength="50"`.

---

## Escenari 7 — *estat de buidor quan no hi ha cap perfil habilitat al sistema*

> Escenari **`test.skip`** quan el seed actual conté entrades fixes.
> S'inclou aquí com a contracte per a entorns sense GPU configurada
> (per exemple, un dev DB net).

### Donat (Given)

1. No hi ha cap GPU al sistema o cap GPU té un perfil habilitat.

### Quan (When)

1. L'admin navega a Bookables → Resources.

### Llavors (Then)

1. La taula `#reservables_vgpus` carrega buida (rebuda buida des de
   `POST /api/v4/admin/table/reservables_vgpus`).
2. DataTables mostra el seu missatge per defecte *No data available
   in table*.

---

## Escenari 8 — *integració amb la pantalla GPUs (cross-check)*

> Escenari **delegat** a [`../gpus.md`](../gpus.md) (Escenaris 5, 6 i
> 13). El test d'aquest fitxer **no** repeteix l'execució; només pot,
> opcionalment, verificar via API que el seed `reservables_vgpus.json`
> i el seed `gpus.json` són consistents abans de la resta del run
> (`gpus[i].profiles_enabled` conté els subitem_ids dels bookables que
> s'esperen a la taula).

---

## Neteja (afterEach)

1. Es recupera el nom original del *bookable* mutat des de
   `testInfo.annotations`.
2. Si el nom, la descripció o el `priority_id` han canviat respecte al
   seed, es restauren via
   `PUT /api/v4/admin/table/update/reservables_vgpus` amb els valors
   originals.
3. Si els alloweds han canviat (Escenari 4), es restauren via
   `POST /api/v4/admin/allowed/update/reservables_vgpus` amb l'estat
   original.
4. Els errors de neteja es silencien per no emmascarar el motiu real
   d'una fallada anterior.

---

## Resultats esperats — resum global

| Escenari | Cobertura prevista | Comprovacions clau |
| --- | --- | --- |
| S1 — Llistar bookables | ✅ | Taula carregada via POST, files esperades del seed |
| S2 — Editar nom/descripció | ✅ | Modal prefillat, dropdown poblat, PUT ok, taula refrescada |
| S3 — Canviar priority_id | ✅ | Dropdown amb opció `default` seleccionable, PUT ok |
| S4 — Alloweds modal | ✅ | POST allowed/table → checkboxes prefills, POST allowed/update aplica canvis |
| S5 — Alloweds viewer al detall | ✅ | Fila expandida, llistat read-only amb `setAlloweds_viewer` |
| S6 — Nom invàlid | ✅ (3/4 casos) | Parsley bloqueja `Send`; cap PUT |
| S7 — Llista buida | ⏭ `skip` | Només aplicable a dev DB sense GPU; el seed actual sempre té files |
| S8 — Cross-check amb GPUs | 🔁 delegat | Cobert a `../gpus.md` |

## API tocades pels fluxos (referència)

- `POST /api/v4/admin/table/reservables_vgpus` — datatable load
  (body `{"order_by":"name"}`).
- `GET  /api/v4/items/bookings/priority-rules` — poblar el dropdown
  *Priority* del modal d'edició. Resposta: `list[PriorityRule]`.
- `PUT  /api/v4/admin/table/update/reservables_vgpus` — actualitzar
  nom, descripció i `priority_id`. Body `{id, name, description,
  priority_id}`.
- `POST /api/v4/allowed/table/reservables_vgpus` — llegir alloweds
  (modal i viewer).
- `POST /api/v4/admin/allowed/update/reservables_vgpus` — actualitzar
  alloweds.

## Estat de base de dades rellevant

- Taula `reservables_vgpus` (un document per perfil de GPU habilitat
  en almenys una GPU del sistema). Cicle de vida controlat per les
  accions de **Hypervisors → GPUs**; aquesta pantalla només **edita**
  metadades.

## Casos no coberts (futurs)

- Edició simultània d'un mateix *bookable* per dos admins (conflicte
  optimista).
- Eliminació d'una regla de prioritat referenciada per un *bookable*
  (verificar que `priority_id` torna a `null` o cau a `default`).
  Bloca el test d'eliminació de la regla a [`priority.md`](priority.md).
- *Bookables* d'un futur tipus diferent de vGPU (avui només existeix
  la taula `reservables_vgpus`).
