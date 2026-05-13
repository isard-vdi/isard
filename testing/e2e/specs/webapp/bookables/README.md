# Bookables — admin webapp

Especificacions funcionals dels tres subapartats del menú **Bookables**
de l'admin clàssic (webapp), llegibles per humans i que serveixen de
contracte per als tests E2E corresponents sota
`testing/e2e/tests/webapp/bookables/`.

## Mapa de pantalles

| Sub-pàgina | URL | Plantilla | JS | Spec |
| --- | --- | --- | --- | --- |
| **Priority** | `/isard-admin/admin/domains/render/Priority` | `templates/admin/pages/bookables_priority.html` | `static/admin/js/bookables_priority.js` | [`priority.md`](priority.md) |
| **Resources** | `/isard-admin/admin/domains/render/Bookables` | `templates/admin/pages/bookables.html` | `static/admin/js/bookables.js` | [`resources.md`](resources.md) |
| **Events** | `/isard-admin/admin/domains/render/BookablesEvents` | `templates/admin/pages/bookables_events.html` | `static/admin/js/bookables_events.js` | [`events.md`](events.md) |

Totes tres pengen de la mateixa entrada de menú «Bookables» de la
barra lateral (`templates/sidebar.html`). El controlador
`render_bookables(nav)` a `webapp/views/AdminViews.py` les distingeix
pel paràmetre `nav`.

## Contracte entre pantalles

```
   ┌──────────────┐      priority_id (FK)      ┌───────────────┐
   │   Priority   │ ◀──────────────────────────│   Resources   │
   │ (rules)      │                            │ (vGPU bookable│
   │              │                            │  metadata)    │
   └──────┬───────┘                            └───────┬───────┘
          │                                            │
          │ rule applied                               │ bookable used by
          ▼                                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │                       Events                              │
   │ plans (#table-planning) + bookings (#table-booking)       │
   │                + booking scheduler (read-only)            │
   └──────────────────────────────────────────────────────────┘
```

- **Priority** defineix les regles (`bookings_priority`) que cada
  *bookable* fa servir com a `priority_id`.
- **Resources** llista els *bookables* del sistema (avui només
  `reservables_vgpus`) i permet editar nom, descripció i la regla de
  prioritat assignada. La **creació i l'eliminació** d'una entrada de
  `reservables_vgpus` **no** són accions d'aquesta pantalla: passen
  com a efecte lateral d'habilitar o inhabilitar un perfil d'una GPU
  des d'**Hypervisors → GPUs** (cobert a [`../gpus.md`](../gpus.md),
  Escenaris 5, 6 i 13).
- **Events** mostra els plans (`resource_planner`), els bookings
  (`bookings`) i els jobs del scheduler de bookings. Llegeix dades
  generades a partir dels recursos de **Resources** i les regles de
  **Priority**.

## Convencions comunes

| Element | Valor esperat |
| --- | --- |
| Rol | Admin de la categoria `default` |
| Sessió | Iniciada a la webapp via la fixture `login.js` (admin per worker) |
| Idioma | Català per a la prosa de l'spec; codi, IDs d'API i selectors en anglès |
| Estructura de cada spec | `Abast` → `Rol i prerequisits` → `Dades comunes` → `Escenaris numerats (Given/When/Then)` → `Neteja` → `Resultats esperats — resum` → `API tocades` → `Estat de base de dades` → `Casos no coberts` |
| Convenció de noms | Recursos creats per un test es prefixen amb `e2e-<area>-<worker>-<timestamp>` i es traquegen via `testInfo.annotations` perquè `afterEach` els pugui netejar encara que el test falli |

## Seeds rellevants del testing DB

Els tests assumeixen presència dels seeds següents (ubicats a
`testing/db/data/`):

- `bookings_priority.json`: regles `default` i `default admins`
  (sistema, no eliminables), i `test-low-forbid-time` (rule_id
  `test-booking-rule`, role `user`).
- `reservables_vgpus.json`: bookables `NVIDIA-A16-2Q`,
  `NVIDIA-A16-4Q` (priority_id `default`), `NVIDIA-T4-2Q`
  (priority_id `test-booking-rule`) i l'entrada sentinella `None`.
- `bookings.json`: dos bookings d'admin lligats a
  `NVIDIA-A16-2Q` dins el plan `24ee2910-…`.
- `resource_planner.json`: plan `24ee2910-…` per a `NVIDIA-A16-2Q` i
  plan `test-t4-2q-available-plan` per a `NVIDIA-T4-2Q`.

Aquests seeds són **compartits** entre workers paral·lels: cap test
ha de mutar-los de manera no idempotent. Si un test necessita
modificar-los, ha de fer-ho sobre una còpia creada al setup del propi
test i restaurar l'estat al `afterEach`.
