# Informe de validació — 26 d'octubre de 2026

Entorn: Python 3.12.14. Dependències exactes a `requirements-dev.lock`.
Projecte instal·lat correctament en mode editable a `work/venv`.

| Comprovació executada | Resultat final |
| --- | --- |
| `work/venv/bin/python -m pytest -q` | **55 passed in 4.11s**; 0 fallades |
| `work/venv/bin/ruff check .` | All checks passed |
| `work/venv/bin/ruff format --check .` | Cap canvi de format necessari |
| `work/venv/bin/python scripts/smoke_offline.py` | Importació repetida: 1 activitat única |
| `work/venv/bin/pip check` | No broken requirements found |
| Instal·lació editable amb pip | Construcció i instal·lació correctes |

## Abast efectivament provat

- FIT binaris sintètics: CRC independent, camps escalats/originals, unitats, HR nul·la,
  absència d'altitud, pauses, intervals irregulars i duplicats conservats.
- FIT invàlids, truncats, CRC alterat i multisessió rebutjats.
- Identitat per hash, ID explícit i serial/inici/esport, reimportació idempotent,
  versions modificades, enriquiment API i conflictes potencials marcats.
- Importació de directori, ZIP, ZIP imbricat, rutes `../` sense extracció, límits
  acumulats/membres/profunditat, resum JSON i format desconegut.
- SQLite real: persistència entre connexions, rollback i integritat d'originals.
- Temps GMT/UTC i offsets, preservació de data local sense zona inventada.
- API simulada: aprovació necessària, autenticació, caducitat, primer 401 i renovació,
  límit local de freqüència, 429/500/503, backoff, reintents exhaurits i errors de xarxa.
- Retry-After llarg ajornat, límit de mida, redireccions rebutjades, errors sense cos
  sensible, esquemes de token/cerca desconeguts i ID amb intent de travessia rebutjats.
- Paginació, pàgina repetida, límit de pàgines, descàrregues incrementals, refresc,
  fallada/represa i atomicitat quan falla la segona activitat d'una pàgina.
- CLI offline sense clau i bloqueig de `sync` abans de llegir credencials.
- Auditoria persistent d'importacions i cobertura sempre no verificada.

Sortida del smoke test (simulada, no personal):

```json
{
  "synthetic": true,
  "unique_activities": 1,
  "coverage": "Cobertura no verificada",
  "repeat_import": "idempotent"
}
```

## Pendent i no verificat

1. Esquemes complets i paràmetres OpenAPI, inclòs el retorn del token.
2. Injecció real del Network secret, permisos del compte i quotes Garmin.
3. Descàrrega real, inventari complet, dates extremes reals i discontinuïtats.
4. Variants d'exportació d'un compte real i fitxers multiesport.
5. PostgreSQL, migracions, volum persistent i rendiment a gran escala.
6. Execució de GitHub Actions en remot: el workflow s'ha creat però no s'ha llançat.
7. Motors fisiològics, dashboard i automatització: fora de fase 1.

No s'ha executat cap petició autenticada ni s'ha publicat res. Els resultats amb mocks
validen el comportament del programa per al perfil simulat; no validen el contracte
real ni certifiquen que tot l'historial Garmin sigui accessible.

## Revisió de tancament de fase 1

Nova execució: **55 proves superades, 0 fallades**. La suite prohibeix connexions reals
amb una fixture autouse; les execucions s'han fet amb GARMIN_API_KEY eliminada de
l'entorn del procés de proves. Les claus literals dels mocks són fictícies.

Proves noves: nova petició amb `Authorization: ApiKey` en caducar, cap ús de refresh
token encara que aparegui a la resposta simulada, rebuig de caducitat booleana, DB
aliena/incompatible intacta i restauració conjunta de DB + originals amb dues versions.

Comprovacions de seguretat executades:

- Escaneig dels 31 candidats a Git: cap patró detectat de clau privada, token de servei,
  JWT, credencial a URL, FIT binari, DB SQLite ni exportació privada. Revisió manual
  dels literals d'autenticació: ruta pública i valors sintètics. Sis regles d'exclusió
  comprovades. L'únic FIT de smoke coincideix byte a byte amb el generador sintètic.
- Bandit 1.9.4, `bandit -r src`: 3 avisos LOW, 0 MEDIUM, 0 HIGH. B105 identifica
  incorrectament TOKEN_PATH (ruta pública) com a contrasenya; dos B311 corresponen
  a random.random per jitter de backoff, sense funció criptogràfica. Revisats,
  no ocultats amb supressions. El procés Bandit retorna 1 per aquests avisos.
- pip-audit: 15 dependències fixades auditades contra PyPI, cap vulnerabilitat coneguda.
  Ordre: `pip-audit -r requirements-dev.lock --no-deps --disable-pip
  --vulnerability-service pypi`. No s'hi han enviat dades d'activitats ni credencials.
- `pip check`: correcte. Ruff check i format: correctes. Smoke offline: correcte.

Limitacions: els escaneigs són heurístics, no una certificació d'absència de secrets.
L'auditoria de dependències cobreix el lock, no extensions futures, Python, sistema
operatiu, serveis externs o dependències de build no fixades. La revisió de privacitat
cobreix els fitxers preparats per Git; work/ conté eines, cachés i dades sintètiques i
queda exclòs. No s'ha consultat el valor real de cap secret ni s'ha cridat Garmin.

La connexió oficial continua pendent del contracte complet. Les FAQ confirmen
ApiKey, OAuth2, vigència i absència de refresh tokens; això no verifica els DTO.
