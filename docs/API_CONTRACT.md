# Contracte oficial Garmin — revisió del 26 d'octubre de 2026

## Fonts i abast de verificació

- [Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/).
- [FAQ oficial](https://developer.garmin.com/gc-developer-program/personal/personal-faq/).
- [Swagger oficial](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/).

Personal API i FAQ s'han pogut consultar amb el lector web. La versió indexada del
Swagger mostra les rutes, però no els detalls complets dels paràmetres ni esquemes.

La consulta directa al Swagger des del contenidor ha fallat amb `CONNECT tunnel
failed, response 403`: és un rebuig del proxy, anterior a una resposta de Garmin
(`http_code=000`), no una prova que Garmin retorni 403. No s'ha eludit la restricció,
canviat la política de xarxa ni provat rutes alternatives. No s'ha descarregat
l'especificació OpenAPI; no en podem proporcionar una versió/checksum verificats.

## Autenticació confirmada

- Host: `https://personal.connectapi.garmin.com`.
- Token: `POST /personalapitoken-service/personal-api/personal-api-key/token`.
- Capçalera: `Authorization: ApiKey <credencial>`.
- El resultat és un access token OAuth2; la clau no autentica directament els recursos.
- Segons les FAQ, vigència màxima de 24 hores o fins a caducar la clau, el que passi abans.
- Garmin **no admet refresh tokens**: cal obtenir un token nou amb la mateixa petició.

El codi segueix aquest flux: token només en memòria; nova petició amb ApiKey en
caducar o després del primer 401. No desa, envia ni utilitza refresh tokens. Les
proves ho comproven amb un transport simulat, sense llegir cap credencial real.

## Rutes contrastades i perfil provisional del client

| Ruta | Confirmat a l'índex oficial | Pendent de contrast complet |
| --- | --- | --- |
| `GET /activitylist-service/activities/search/activities` | Cerca d'activitats paginada | Noms, tipus, límits, filtres, ordenació, resposta i final de paginació |
| `GET /activity-service/activity/{activityId}` | Detall d'activitat | Tipus de l'ID, camps, nul·labilitat i unitats del DTO |
| `GET /download-service/files/activity/{activityId}` | Descàrrega d'activitat | Content-Type, contenidor FIT/ZIP i errors possibles |

El client assumeix provisionalment `start`/`limit`, una llista JSON amb `activityId`,
`access_token`, `expires_in` en segons i `Authorization: Bearer <token>` per als
recursos. Aquests noms i esquemes encara **no estan verificats** contra l'OpenAPI.
El client exigeix caducitat explícita; no inventa `expires_in=86400` a partir de la FAQ.

Els límits locals (1 s entre peticions, 100 elements màxims per pàgina, reintents i
mides màximes) no són quotes oficials. Retenció històrica, rate limits, codis d'error,
permisos i exhaustivitat continuen pendents. La cobertura és «Cobertura no verificada».

## Condicions per habilitar la connexió real

1. Obtenir legítimament l'OpenAPI públic complet i registrar data, versió i checksum.
2. Contrastar tots els detalls pendents, adaptar el client i afegir fixtures sintètiques.
3. Tornar a executar les proves i revisar el mecanisme de secrets.
4. Disposar d'aprovació explícita abans de qualsevol petició autenticada.

`--contract-verified` no s'ha habilitat per a xarxa real. Les proves amb mocks no
certifiquen conformitat amb Garmin. En aquesta revisió no s'ha fet cap petició
autenticada, no s'ha llegit l'API Key i no s'ha iniciat la fase 2.
