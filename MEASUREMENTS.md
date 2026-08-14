# Finalize path — mesures verificades

Totes preses a la VM d'staging `lt5026` (8 vCPU / 26 GB), instal·lació neta amb 135 escriptoris
de bootstrap, perfil de càrrega `queues` a **25 VUs durant 3 minuts**, i el perfilador dins del
change-handler amb informe cada **5.400 entrades**.

El perfilador embolcalla `RqlQuery.run` i `Redis.execute_command` de manera global, o sigui que
els totals de RethinkDB i Redis inclouen també les altres corrutines del procés (changefeed,
reconcile, productor de cues). **Les fases sí que són per entrada d'assentament** i són la mesura
de referència.

## Latència de la base de dades, aïllada

Micro-benchmark sobre la mateixa BD, sense càrrega (25 iteracions):

| operació | ms |
|---|---|
| `domains.get(id)` | **0,21** |
| `domains.update` (per defecte, `durability=hard`) | **7,55** |
| `domains.update` amb `durability="soft"` | 3,72 |
| `domains.update` amb `noreply=True` | 0,03 |
| mida del document `domains` | 1.963 bytes |
| mida del document `storage` | 1.347 bytes |

**Conclusió:** el cost d'escriure no és la mida del document ni la CPU — és **latència d'espera de
confirmació**. Una lectura per clau és 36 vegades més barata que una escriptura per clau. Sota
càrrega l'escriptura puja de 7,55 a ~16 ms.

Cap escaneig de taula al camí calent: `storage.parent` i `domains.storage_ids` existeixen.

## Base: `origin/main`

**38,39 ms per entrada** (5.400 entrades).

| fase | ms/entrada | n/entrada |
|---|---|---|
| `run_handler.storage_update` | 11,87 | 0,66 |
| `run_handler.domain_change_storage` | 11,43 | 0,34 |
| `emit_feedback` | 10,16 | 1,00 |
| `set_job_status` | 1,37 | 1,00 |
| `apply_row_progress` | 0,79 | 1,00 |
| `hydrate_task` | 0,73 | 1,00 |
| `save_meta` | 0,44 | 0,66 |
| `update_status` | 0,00 | 0,34 |

RethinkDB més car: `domains update` **9,71 ms/entrada** (0,67 crides/entrada).

## Fase 1 — separar el fan-out (DESCARTADA)

Branca `perf/split-the-fanout-off-the-finalize-path`, no fusionada.

Efecte mesurat sobre la fase d'emissió: **10,16 → 5,31 ms/entrada** (la meitat cara marxa a
l'altre grup). Però l'A/B de punta a punta **no mou res**:

| | main | amb la separació |
|---|---|---|
| lag màxim del grup d'assentament | 858 | 882 |
| p95 de creació interactiva | 34,21 s | 34,19 s |
| total per entrada | 38,39 ms | 37,95 ms |

Correcta i sense pèrdues (els dos grups llegeixen les mateixes 48.768 entrades), però el guany
és massa petit contra el que dominen els gestors. **Descartada per decisió de l'usuari.**

## Multiplicadors estructurals trobats al codi (verificats)

A `connections/rethink_base.py`:

- `Model(id)` = **2 viatges sempre** (`exists()` i després `get()`); el `get` ja retorna `None`
  si la fila no hi és, o sigui que el primer no aporta informació.
- **Una `UPDATE` per cada assignació d'atribut**; `obj.a = x; obj.b = y` són dues escriptures.
- `init_document` = **3 viatges** (insert + exists + get), i hi ha quatre llocs que llencen el
  resultat.
- `get_index` = **1 + 2N viatges**: demana només els ids i després rellegeix cada fila dues
  vegades. Això és el que multiplica amb la llargada de la cadena.

Al desplegament:

- `RETHINKDB_POOL_SIZE` del change-handler és **5** (apiv4 en té 128), i com que les entrades es
  despatxen d'una en una, mai se'n fa servir més d'una.
- Quatre gestors estan registrats com a **`ASYNC`** (`storage_update`, `storage_update_pool`,
  `storage_update_dict`, `update_status`) i el consumidor els fa `await handler(...)`
  **directament al bucle d'esdeveniments**, tot i que els seus cossos fan crides bloquejants a
  RethinkDB. Mentre corren bloquegen el changefeed, el reconcile, el productor de cues i el
  consumidor de progrés, que comparteixen aquest bucle.

## (a) Guanys gratuïts — VERIFICATS

Branca `perf/cut-the-redundant-round-trips`. Tres canvis:

1. **Cau compartida per a la categoria de l'usuari** (`models/user.py: category_of`, TTL 60 s,
   una lectura en comptes de dues). Els dos llocs que la resolien sense cau
   (`task_results/feedback.py` i `task_results/storage.py`) hi apunten.
2. **Fusionar les dues escriptures a la mateixa fila** dins d'`handle_domain_change_storage`:
   `create_dict` i `status` anaven en dues `UPDATE` separades sobre el mateix document, sense cap
   lectura entremig. Ara és una sola `update_document`, amb `status_time` posat a mà perquè
   aquest camí ja no passa per `__setattr__`.

| | main | amb els guanys | canvi |
|---|---|---|---|
| **total per entrada** | 38,39 ms | **35,63 ms** | **−7,2%** |
| `domain_change_storage` | 11,43 ms | **9,67 ms** | **−15,4%** |
| `emit_feedback` | 10,16 ms | **8,87 ms** | **−12,7%** |
| `storage_update` | 11,87 ms | 11,99 ms | igual |

Els dos mecanismes es poden verificar directament al comptador de queries:

| query | main | amb els guanys |
|---|---|---|
| `domains update` | 3.638 crides (**0,67**/entrada) | 2.201 crides (**0,34**/entrada) |
| `users get` | 29.741 crides (**5,51**/entrada, 4,06 ms/entrada) | **desapareix del perfil** |

Les escriptures a `domains` queden **exactament a la meitat**, que és el que el canvi pretenia, i
les lectures de `users` s'esvaeixen del tot.

## (b) Estructural — PARCIAL, i el primer tall NO és un guany

Canvi provat: treure la feina bloquejant de RethinkDB del bucle d'esdeveniments, embolcallant
`_apply_storage_update` amb `asyncio.to_thread` als dos gestors `ASYNC` que la criden.

| | main | (a) guanys | (a) + `to_thread` |
|---|---|---|---|
| **total per entrada** | 38,39 ms | **35,63 ms** | 36,41 ms |
| `storage_update` | 11,87 ms | 11,99 ms | **13,36 ms** |
| `domain_change_storage` | 11,43 ms | 9,67 ms | 9,48 ms |
| `emit_feedback` | 10,16 ms | 8,87 ms | 8,63 ms |

**Empitjora**, i té sentit: el salt de fil afegeix latència pròpia, i **no compra res mentre les
entrades es despatxin d'una en una**. Alliberar el bucle només val la pena si algú altre pot fer
servir el temps alliberat; aquí qui espera és el mateix bucle d'assentament.

⚠️ A més, la pujada del pool **no es va arribar a aplicar** en aquesta mesura: la variable viu al
compose i el contenidor ja corria amb `POOL=5`. O sigui que aquesta xifra és només del `to_thread`.

**Conclusió:** el `to_thread` i el pool són **prerequisits** del despatx concurrent, no millores
per si soles. No s'han de fusionar sols — o van amb la concurrència, o no van.
