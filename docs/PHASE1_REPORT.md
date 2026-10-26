# Fase 1 — segona revisió de la PR #1

Data: 26 d'octubre de 2026. Branca `codex/phase1-ingestion`.
[PR #1 en esborrany](https://github.com/Dev-Jaume/garmin-analytics/pull/1).
No s'ha iniciat la fase 2, fusionat la PR, desplegat infraestructura ni accedit a Garmin real.

## Contracte oficial

El Swagger directe continua bloquejat pel proxy amb CONNECT 403 (no resposta de Garmin).
S'ha consultat una font primària addicional: el client Python oficial garmin/connect-personal-api-python,
commit ac111a0ff8e37dfbc24c616fcc27691520c7278b.

S'ha corregit la hipòtesi anterior: el token és un JWT en text amb exp, no un JSON
access_token/expires_in. Confirmats Authorization: ApiKey per obtenir-lo, Bearer
per als recursos, start/limit al SDK i ZIP original per a la descàrrega. No hi ha refresh
tokens i la nostra cache continua només en memòria. Detall, evidència i URLs fixades a
`API_CONTRACT.md`. Els DTO complets i semàntica/quotes oficials continuen pendents:
no s'afirma verificació completa ni s'habilita accés real.

## Refactorització i recuperació

HTTP, parsing i staging es fan fora de SQL. Els originals es desen de manera immutable,
amb manifests privats i hashes comprovats abans del commit de la pàgina. Activitats,
versions i checkpoint es comprometen conjuntament; no hi ha SQL obert durant HTTP.

En fallar, les pàgines compromeses queden intactes; la pendent es reprocessa. El staging
íntegre de la mateixa execució evita repetir descàrregues. Si falta un manifest complet
es torna a baixar l'activitat; si està corrupte es conserva i es rebutja. La represa
reinicia el catàleg a zero per reduir omissions causades per desplaçaments d'offset.
No hi ha atomicitat distribuïda filesystem/SQL: les fallades prèvies al commit poden
produir originals orfes, que es conserven; una corrupció posterior necessita backup.

## Auditoria ampliada

Offsets, IDs i hashes per pàgina/intents, duplicats interns i entre pàgines, conflictes,
resums canviats i pàgines repetides. Segona lectura completa del catàleg sense FIT,
amb comparació d'IDs, seqüència i signatures. S'identifiquen possibles omissions,
altes/baixes o canvis de resum sense assumir que salts numèrics siguin dades perdudes.

Una reconciliació diferent/incompleta o incidències marca `unstable`; `exhausted`
només indica dues lectures observades com a estables, sense provar historial complet.
La cobertura es manté «Cobertura no verificada». Cal inventari extern i controlar
quotes abans de fer dues passades reals.

## Persistència: dues propostes sense desplegar

A `ARCHITECTURE.md` s'especifiquen:

- A: DigitalOcean Droplet 2 GiB + SQLite en volum LUKS 20 GiB + restic xifrat a Spaces
  privat. Base calculada $19/mes, pressupost orientatiu $19–25, abans d'impostos.
- B: PostgreSQL gestionat 1 GiB + worker 2 GiB + volum LUKS i Spaces.
  Base $34.15/mes, amb reserva de 10 GiB DB addicionals $36.30; pressupost $35–45, abans d'impostos. Migració i proves
  PostgreSQL encara necessàries; originals al volum privat persistent.

Preus consultats a fonts oficials, costos variables i treball humà exclosos. S'hi
expliquen avantatges, inconvenients, TLS/VPC, gestió de claus i backup/restauració.
Codex treballa amb codi/fixtures; la producció es manté al worker. Accés VPN/TCP
només amb configuració i autorització futures. Recomanació inicial A per un escriptor.

## Validació i privacitat

82 proves superades, 0 fallades; Ruff, pip check i smoke correctes. Proves noves de
fallades de xarxa/disc/SQL, interrupcions, staging, represa, detecció de canvis de
catàleg i contracte JWT. Resum detallat a `VALIDATION.md`.

pip-audit: 15 dependències, cap vulnerabilitat coneguda. Bandit: tres avisos baixos
revisats (ruta pública i jitter), cap mitjà/alt. Revisió de candidats a publicació sense
secrets reals, FIT, DB ni dades personals detectades. Només fixtures sintètiques;
cap credencial Garmin llegida ni utilitzada. Tests amb xarxa real prohibida.
