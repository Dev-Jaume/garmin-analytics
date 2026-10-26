# Validació de la segona revisió de fase 1 — 26 d'octubre de 2026

Entorn Python 3.12.14; dependències del projecte fixades a `requirements-dev.lock`.
Totes les dades d'entrada són sintètiques. La fixture autouse prohibeix connexions de
xarxa reals; les execucions s'han fet amb GARMIN_API_KEY retirada del procés de tests.

| Ordre/comprovació | Resultat local |
| --- | --- |
| `env -u GARMIN_API_KEY work/venv/bin/python -m pytest -q` | **82 passed in 4.81s**, 0 fallades |
| `ruff check src tests scripts` | Correcte |
| `ruff format --check src tests scripts` | Correcte |
| `python scripts/smoke_offline.py` | Dues importacions, una activitat sintètica única |
| `pip check` | Cap dependència trencada |
| `pip-audit -r requirements-dev.lock --no-deps --disable-pip --vulnerability-service pypi` | 15 dependències, cap vulnerabilitat coneguda |
| `bandit -r src` | 3 avisos LOW revisats, 0 MEDIUM/HIGH |
| Revisió heurística/manual dels candidats a Git | Sense secrets reals, FIT ni DB detectats |

## Contracte i autenticació

JWT en text amb claim exp, capçaleres ApiKey/Bearer/Accept, absència de refresh-token,
renovació en caducar i després de 401, JSON antic rebutjat, JWT malformats/caducats
rebutjats (incloent exp booleà, nul, text o infinit), IDs ASCII positius, redireccions
rebutjades, límits de mida, paginació i errors/reintents HTTP. Fixtures contrastades
amb el client Python oficial Garmin, revisió fixada a `API_CONTRACT.md`.

Això valida el nostre comportament davant el perfil simulat. No s'ha fet una prova
contra Garmin ni obtingut l'OAS complet: DTO, garanties de paginació i cobertura
històrica real continuen pendents.

## Ingesta i persistència

FIT binaris amb CRC independent, camps/units/nuls, irregularitats i duplicats,
ZIP imbricats i rutes sense extracció, límits i errors d'importació, identitat/versionat,
enriquiment API preservat i resums conservadors. SQLite real: rollback, persistència
entre connexions, DB incompatibles intactes i backup/restauració de dues versions
amb verificació d'originals i integritat. No s'ha provat PostgreSQL ni infraestructura.

## Fallades i auditoria de sincronització

- Instrumentació SQLAlchemy comprova que no hi ha cap transacció SQL durant cap
  petició HTTP: token, cerca, detall, descàrrega o reconciliació.
- Fallada de xarxa a la segona activitat després de preparar la primera: cap activitat
  compromesa de la pàgina, checkpoint intacte i represa reutilitzant el primer staging.
- Error de disc després de descarregar però abans d'arxivar: cap referència SQL; la
  represa torna a descarregar perquè no hi ha manifest complet.
- Error SQL després del primer insert d'una pàgina: rollback conjunt i posterior
  represa amb els dos staging preparats, sense repetir descàrregues.
- KeyboardInterrupt a mitja pàgina: estat interrupted i represa idempotent.
- Fallada entre pàgines: pàgina ja compromesa conservada, represa des de zero i sense
  duplicació; fallada de xarxa en reconciliació també recuperable.
- Manifest manipulat o original absent: represa bloquejada abans d'escriure SQL.
- Duplicats dins de pàgina, conflictius i entre pàgines; pàgina repetida i límit de pàgines.
- Inserció al cap, supressió durant la passada, resum canviat entre passades,
  verificació incompleta i IDs del catàleg anterior que no reapareixen: inestabilitat
  registrada sense esborrar activitats locals ni afirmar exhaustivitat.
- IDs numèricament no contigus no generen falses omissions.

No són proves de tall físic d'alimentació, SIGKILL real, accés concurrent de múltiples
sincronitzadors, corrupció arbitrària de disc ni grans volums en producció.

## Seguretat i límits de l'auditoria

Bandit 1.9.4 conserva els tres avisos, sense supressions: B105 assenyala TOKEN_PATH,
una ruta pública; els dos B311 són jitter de backoff, sense cap funció criptogràfica.
El procés Bandit retorna 1 pels avisos; no s'ha presentat com una execució sense avisos.

pip-audit 2.10.1 consulta només metadades públiques de les 15 dependències del lock a
PyPI. No envia salut, ubicacions ni credencials. No cobreix SO, Python, futura
infraestructura ni dependències de build no fixades.

Revisió del conjunt de fitxers versionats + nous: patrons de claus privades, tokens
de servei, JWT literals, credencials a URL, capçaleres binàries FIT/SQLite i extensions
privades. L'únic FIT del smoke coincideix amb el generador sintètic. Regles Git
verificades per a .env, FIT, exportacions, DB, claus i work/. Els resultats/cachés de les
eines i staging sintètic queden a work/, fora de Git. És una revisió heurística/manual,
no una demostració formal d'absència de secrets. No s'han llegit valors de credencials.

GitHub Actions a la PR és una comprovació separada: el workflow executa pytest i Ruff;
Bandit i pip-audit s'han executat localment en aquesta revisió. L'estat remot actual
es consulta als checks de la PR, no s'infereix dels resultats locals.
