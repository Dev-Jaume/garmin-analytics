# Contracte Garmin — segona revisió del 26 d'octubre de 2026

## Evidència primària i límits

- [Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/).
- [FAQ oficial](https://developer.garmin.com/gc-developer-program/personal/personal-faq/).
- [Swagger oficial](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/).
- [Client Python publicat per Garmin](https://github.com/garmin/connect-personal-api-python/tree/ac111a0ff8e37dfbc24c616fcc27691520c7278b),
  revisió fixada `ac111a0ff8e37dfbc24c616fcc27691520c7278b`.

La nova consulta directa al Swagger ha rebut `CONNECT tunnel failed, response 403`
del proxy (`http_code=000`): no és una resposta HTTP rebuda de Garmin. No s'ha eludit
la restricció ni canviat la política. El lector web mostra la pàgina però no l'OAS
interactiu complet. El client oficial a GitHub és una font pública independent,
consultada sense credencials Garmin. No s'han emprat clients comunitaris com a prova
de conformitat, ni s'ha executat el codi oficial sobre cap compte.

## Matriu de verificació

| Aspecte | Evidència oficial | Estat i implementació |
| --- | --- | --- |
| Host | `constants.py` | `https://personal.connectapi.garmin.com` confirmat |
| Token | `auth.py`, FAQ | `POST /personalapitoken-service/personal-api/personal-api-key/token`, `Authorization: ApiKey <clau>`, `Accept: */*` |
| Esquema del token | `auth.py`, `tests/test_auth.py` | **JWT en text**, no JSON `access_token`/`expires_in`; claim `exp` per a caducitat |
| Autenticació de recursos | `client.py`, `tests/test_client.py` | `Authorization: Bearer <JWT>`; `Accept: application/json` per a JSON |
| Paginació | `client.py:search_activities`, tests oficials | Query `start` i `limit`; defaults del SDK 0 i 20; també `startDate`, `endDate`, `activityType` |
| Cerca | `client.py:search_activities` | `GET /activitylist-service/activities/search/activities`, resposta JSON; DTO complet pendent |
| Detall | `client.py:get_activity` | `GET /activity-service/activity/{activityId}`, resposta JSON; DTO complet pendent |
| Descàrrega | `client.py:download_activity`, README i tests | `GET /download-service/files/activity/{activityId}`, ZIP binari original |
| Headers de descàrrega | `client.py:download_activity` | `Accept: application/zip, application/x-zip-compressed, application/octet-stream`; Bearer |
| ID de descàrrega | `client.py` i tests oficials | Enter positiu ASCII; zeros, negatius i dígits Unicode rebutjats |

Referències exactes: [auth.py](https://github.com/garmin/connect-personal-api-python/blob/ac111a0ff8e37dfbc24c616fcc27691520c7278b/src/garmin_personal_api/auth.py),
[client.py](https://github.com/garmin/connect-personal-api-python/blob/ac111a0ff8e37dfbc24c616fcc27691520c7278b/src/garmin_personal_api/client.py),
[tests d'autenticació](https://github.com/garmin/connect-personal-api-python/blob/ac111a0ff8e37dfbc24c616fcc27691520c7278b/tests/test_auth.py)
i [tests del client](https://github.com/garmin/connect-personal-api-python/blob/ac111a0ff8e37dfbc24c616fcc27691520c7278b/tests/test_client.py).

La hipòtesi anterior del token JSON era incorrecta i s'ha substituït. La nostra
implementació pròpia interpreta `exp` només per gestionar la memòria cau: no verifica
la signatura JWT ni tracta les seves claims com a autorització. TLS autentica la
resposta del servidor i Garmin valida el token dels recursos. Es renova anticipadament,
amb màxim local de 24 h, sense persistir tokens. Les FAQ fixen la vigència màxima en
24 h o la caducitat de la clau, el que passi abans. No hi ha refresh tokens: en caducar
o després del primer 401 es fa una nova petició amb ApiKey.

## Allò que la referència oficial no permet certificar

El SDK retorna JSON genèric i no imposa DTO complets. La llista de resums amb
`activityId` i l'objecte de detall són encara el perfil estricte del nostre adaptador,
provat amb fixtures sintètiques; no es presenten com un esquema OAS verificat.
Camps obligatoris/opcionals, nul·labilitat, unitats, embolcalls, límits oficials,
ordenació estable, retenció històrica i errors específics continuen pendents.

Els defaults del SDK no demostren els defaults ni les quotes del servidor. El límit
local 1–100 i la interpretació d'una pàgina buida com a final requereixen contrast OAS.
Dues passades iguals només aporten estabilitat observada; la cobertura continua com a
**«Cobertura no verificada»**. No s'infereixen omissions de salts numèrics en IDs.

El ZIP és oficial; acceptar un FIT directe és només compatibilitat defensiva local.
S'exigeix exactament un FIT no xifrat dins dels límits de mida, CRC correcte i una
sessió interpretable. No s'afirma que tots els ZIP Garmin compleixin aquesta política:
ZIP amb diversos FIT, altres formats o multiesport es rebutgen sense perdre l'original.
El Content-Type exacte retornat pel servidor encara no s'ha observat ni certificat.

## Pendent per completar el contracte

Obtenir legítimament l'OAS públic complet, registrar-ne versió i SHA-256, validar els
DTO i semàntica de paginació i afegir fixtures de contracte. No s'ha inventat un hash
d'una especificació que no hem pogut obtenir. No s'han habilitat les opcions de
connexió real, llegit claus, cridat dades Garmin ni iniciat la fase 2.
