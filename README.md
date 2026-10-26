# Garmin Running Analytics

Plataforma personal en català. **Fase 1 funcional en mode offline**, amb importació
FIT/exportacions, SQLite, auditoria i client oficial provat amb mocks. La connexió
real continua bloquejada fins a l'aprovació del mecanisme de secrets i la verificació
del contracte de l'API. No s'ha accedit al compte Garmin ni s'han utilitzat dades reals.

## Arquitectura implementada

- `src/garmin_running/domain.py`: activitat normalitzada, instants UTC i camps opcionals.
- `fit/parser.py`: fitdecode amb CRC i errors estrictes; sessions, voltes, registres,
  esdeveniments, dispositiu, valors originals i unitats. El FIT es manté byte a byte.
- `ingestion/importer.py`: FIT individuals, directoris, ZIP i ZIP imbricats; límits
  de mida i profunditat, errors per entrada i adaptador conservador de resums JSON.
- `storage/repository.py`: SQLAlchemy, activitats, àlies, versions, execucions de
  sincronització/importació, esquema versionat i arxiu immutable per SHA-256.
- `garmin/client.py`: només el domini Personal API, token en memòria, renovació,
  reintents limitats, Retry-After, limitació de freqüència i mida, sense redireccions.
- `garmin/sync.py`: paginació, transacció per pàgina, checkpoints, represa des de zero amb staging,
  signatures de resum per evitar descàrregues repetides i refresc complet opcional.
- `cli.py`: `init`, `import`, `coverage` i `sync` amb dues barreres explícites.
- `tests/`: FIT binaris sintètics amb CRC independent i API HTTP simulada.
- `.github/workflows/tests.yml`: proves i Ruff sense secrets.

No hi ha dashboard, estimacions fisiològiques ni VDOT en aquesta fase. Prioritzem
la importació abans d'afegir dependències de visualització o algoritmes fisiològics.

## Execució

L'entorn d'aquesta tasca ja té les dependències instal·lades a `work/venv` i les
proves executades. Les ordres següents documenten la reproducció; no cal copiar
codi ni crear fitxers manualment.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/gra init
.venv/bin/gra import /ruta/privada/exportacio-garmin.zip
.venv/bin/gra coverage
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

La CLI crea `private/analytics.sqlite3` i `private/originals/`, ignorats per Git.
Per dades reals, cal un volum privat amb persistència i còpia de seguretat externa.
`--data-dir /volum/privat` i `--database-url` són opcions globals, abans de l'ordre.
`.env.example` és documentació: l'aplicació no carrega fitxers `.env` automàticament.

## Importació i deduplicació

Podeu proporcionar directament l'exportació completa Garmin en ZIP, un directori
ja descomprimit o un FIT. No s'extreuen rutes del ZIP al sistema de fitxers. Els
ZIP imbricats s'inspeccionen fins al límit configurat; els altres formats es compten
com a ignorats. El recompte `imported` indica entrades acceptades, inclosos reimports
idempotents; el nombre d'activitats úniques apareix a `coverage`.

1. `activityId` verificat, quan està disponible.
2. SHA-256 per a còpies exactes.
3. Dispositiu (serial), inici UTC i esport per a versions FIT sense activityId.
4. Sense identificació suficient es conserva una activitat separada; coincidències
   d'inici/esport queden marcades com a possibles duplicats. No s'infereix l'ID del nom.

Per vincular un FIT individual amb un ID conegut: `gra import fitxer.fit --activity-id 123`.
Un conflicte entre identitats ja existents es rebutja perquè requereix reconciliació.
No es fusionen automàticament activitats amb distàncies o hores només semblants.
Les versions preserven el FIT i la representació derivada; reimportar una versió
ja existent no reverteix la versió actual.

Els FIT multisessió/multiesport es rebutgen explícitament i se'n conserva l'original:
la descomposició sense perdre transicions requereix un adaptador posterior.
Els resums JSON compatibles tenen l'estructura `[{"summarizedActivitiesExport": [...]}]`.
Es conserven sense assumir les unitats de distància/durada. No substitueixen un FIT.
Altres variants JSON, CSV, TCX i GPX encara no estan implementades.

## Cobertura històrica

`coverage` informa dates mínima/màxima, activitats sense data o registres, possibles
duplicats, intervals de 30 dies o més (configurables a la capa de repositori), pàgines
consultades, estat de cada sincronització i errors d'importació persistits.
Un interval sense activitats és un indici per revisar, no una prova de dades perdudes.
L'estat sempre és **«Cobertura no verificada»** fins a un contrast extern documentat.

La sincronització torna a consultar el catàleg des de l'offset zero i només torna a
baixar FIT quan canvia el resum. `--refresh` força relectura de detalls i FIT: necessari
si Garmin modifica una activitat sense canviar el resum. No propaga eliminacions
remotes. La represa torna a l'offset zero i reutilitza staging íntegre; no ofereix garanties de snapshot amb offsets
mutables. Les interrupcions poden deixar originals orfes, però no pàgines parcials a DB.

## Documentació i següent pas

- [Seguretat i configuració de Codex Web](docs/SECURITY.md).
- [Fonts oficials i contracte pendent](docs/API_CONTRACT.md).
- [Disseny, decisions i límits](docs/ARCHITECTURE.md).
- [Informe de validació](docs/VALIDATION.md).

Següent pas: revisar el mecanisme de secrets i completar el contrast del contracte
OpenAPI abans de qualsevol petició autenticada. L'alternativa offline ja es pot
utilitzar sense API Key. Les fases 2–4 s'implementaran després de validar la ingesta.

## Tancament de fase 1

La segona revisió ha executat 84 proves, Ruff, Bandit i pip-audit. Les FAQ oficials
confirmen que no hi ha refresh tokens. Swagger continua parcialment verificat a
causa del 403 del proxy; no s'ha fet cap petició autenticada. La persistència fora de
Codex, el procediment de backup/restauració i la futura migració estan documentats a
`docs/ARCHITECTURE.md`. La implementació i les proves de recuperació es revisen a la PR #1, sense dades reals.

Amb autorització explícita, s'ha inicialitzat main únicament amb el commit buit
`86ef58c` i s'ha publicat la implementació a `codex/phase1-ingestion`. La
[PR #1](https://github.com/Dev-Jaume/garmin-analytics/pull/1) està oberta en esborrany;
no s'ha fusionat ni desplegat res. Els documents es poden consultar a la branca de la PR.

La sincronització prepara originals i manifests privats fora de SQL, compromet cada
pàgina amb el seu checkpoint i fa una segona lectura del catàleg. Discrepàncies es
marquen com `unstable`; no impliquen eliminacions remotes ni cobertura completa.
El token s'interpreta com JWT en text amb exp, contrastat amb el client Python oficial.
Els DTO complets encara requereixen l'OAS; no s'ha habilitat accés autenticat.
