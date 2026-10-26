# Revisió de tancament de fase 1 — 26 d'octubre de 2026

## Estat funcional i contracte

Importació offline implementada amb Python 3.12, SQLAlchemy, SQLite i fitdecode.
Es conserven originals, versions, registres, pauses, unitats i errors d'importació.
Client i sincronitzador paginat provats només amb transport simulat.

Les FAQ oficials confirmen generació OAuth2 amb Authorization: ApiKey i absència
de refresh tokens. El client renova mitjançant una nova petició de token; una prova
comprova també que ignora un refresh_token hipotètic retornat pel mock.

El Swagger complet continua inaccessible: rebuig CONNECT 403 del proxy, no resposta
403 de Garmin. No s'ha eludit el bloqueig. Rutes visibles a l'índex, però paràmetres,
esquemes i capçalera de recursos encara provisionals. Detall a `API_CONTRACT.md`.

## Canvis sorgits de la revisió

- Validació de versió abans de crear taules; DB alienes/incompatibles queden intactes.
- Rebuig de caducitat booleana del token.
- Xarxa real prohibida a tota la suite; execució sense GARMIN_API_KEY heretada.
- Proves explícites de no ús de refresh tokens i backup/restauració conjunta.
- Exclusió Git ampliada per formats FIT/ubicacions i fitxers de claus.
- CI preparada per instal·lar el lock auditat i la versió local sense canviar dependències.

## Resultats i privacitat

55 proves superades; Ruff correcte; smoke idempotent i pip check correctes.
pip-audit: 15 dependències, cap vulnerabilitat coneguda. Bandit: 3 avisos baixos
revisats (ruta pública i jitter), cap mitjà/alt. Vegeu `VALIDATION.md`.

Revisats els 31 fitxers candidats a publicació: sense credencials reals, dades de
salut, FIT reals, ubicacions ni DB privades detectades. Només fixtures sintètiques.
Cap petició autenticada a Garmin, cap desplegament i cap fase 2 iniciada.

## Persistència

Codex Cloud és temporal. Magatzem canònic proposat: SQLite + originals en volum privat
persistent extern i xifrat. Còpies conjuntes amb escriptors aturats, SQLite backup API,
segona còpia privada i restauracions verificades amb hashes i integritat. Patró provat
amb dades sintètiques; infraestructura persistent encara no seleccionada/aprovisionada.
PostgreSQL privat futur requereix migració provada; canviar l'URL no trasllada l'historial.
Procediment complet a `ARCHITECTURE.md`.

## Publicació per Pull Request

Destí: Dev-Jaume/garmin-analytics, públic. Inicialment no tenia cap branca base.
Després de l'autorització explícita de l'usuari s'ha publicat únicament el commit
buit `86ef58c` com a main i la implementació revisada a `codex/phase1-ingestion`.

[PR #1 en esborrany](https://github.com/Dev-Jaume/garmin-analytics/pull/1), amb 31
fitxers de codi, tests, configuració i documentació. El commit d'implementació és
`42c2623`; les actualitzacions posteriors de documentació no alteren el codi provat.
No s'ha fusionat la PR, fet force-push ni desplegat cap servei. Les dades privades,
FIT i DB continuen fora de Git. No s'ha fet cap petició autenticada a Garmin.

L'estat actual de GitHub Actions es pot consultar a la PR. Els resultats locals
verificats són els de `VALIDATION.md`; no s'han de confondre amb una execució remota.
Inventari exacte a `FILES.md`.
