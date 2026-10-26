# Mecanisme proposat de secrets i configuració de Codex Web

## Estat observat, sense llegir credencials

El 26 d'octubre de 2026, l'eina oficial de l'entorn ha informat:

- Connexió de l'entorn disponible.
- Política desitjada restringida, amb `personal.connectapi.garmin.com` i grups per
  instal·lar dependències. En la revisió actual la política consta com a `enforced`,
  amb observacions actuals; inicialment constava com a `unknown`.
- Una vinculació de secret anomenada `GARMIN_API_KEY`, variable del mateix nom,
  limitada al domini Personal API. Estat `ready` en la revisió actual.
- Cap variable de runtime ordinària ni identitat de sortida declarada.

No s'ha llegit el valor de la clau, canviat aquesta configuració ni fet cap petició
autenticada. Els valors anteriors són metadades, no una prova d'accés a Garmin
ni una autorització per utilitzar la clau; la instrucció actual prohibeix aquest accés.

## Flux proposat perquè es pugui revisar

1. En execució explícita de `sync`, llegir només la vinculació `GARMIN_API_KEY`.
   No carregar `.env` ni descobrir credencials llegint fitxers o l'entorn complet.
2. Passar la vinculació opaca al header `Authorization: ApiKey ...` de l'endpoint
   oficial de token, sempre mitjançant el proxy i CA de l'entorn.
3. Conservar el token retornat únicament en memòria. Fer una nova petició de token
   quan caduqui o després del primer 401; no assumir un refresh token.
4. Fer les peticions de recursos amb token. No seguir redireccions. URL base fixa;
   únicament IDs numèrics. Errors sense cossos HTTP, headers ni credencials.
5. Guardar salut, ubicacions i originals en DB/arxiu privat, fora de Git. No enviar-los
   a cap servei de visualització o telemetria. No publicar cap dashboard.

La CLI requereix **dues opcions explícites**: `--secrets-approved` i
`--contract-verified`. No s'han utilitzat en aquest treball, excepte simulacions
unitàries amb `httpx.MockTransport` i claus fictícies. Aquestes opcions són una
barrera operativa, no un sistema d'autorització multiusuari.

## Network secrets i Environment variables

Un **Network secret** pot estar mediat pel proxy. El procés Python pot veure un
marcador, no la clau real. `os.environ.get(...)` no demostra que sigui una credencial
usable directament. No imprimir el valor ni comprovar-lo per comparació amb una
clau copiada. Cal confirmar que el mecanisme de l'entorn suporta la substitució
al header oficial amb la vinculació i domini declarats.

Una **Environment variable** ordinària és configuració llegible pel procés; no
l'hem de tractar automàticament com un gestor segur. Una variable de runtime
classificada com a secret pel servei pot proporcionar un altre mecanisme segur,
però s'ha de revisar explícitament. No traslladar la clau a una variable ordinària
per resoldre una incompatibilitat del proxy.

La implementació accepta la vinculació opaca. Si la plataforma no suporta el flux
al header oficial, la connexió real continua bloquejada: cal un mecanisme de runtime
segur compatible i una nova revisió. Les proves actuals no verifiquen la injecció real.

## Passos a la interfície — només després de l'aprovació

1. Al compte Garmin Connect Web, obrir **Personal API Key** des de la pàgina oficial
   Personal API. Escollir **Create Key**, acceptar les condicions, seleccionar la
   caducitat i protegir la clau mostrada una única vegada. No enganxar-la al xat.
2. A Codex Web, obrir la configuració de l'entorn vinculat a aquesta tasca. Revisar
   l'apartat **Network secrets**: existeix una vinculació `GARMIN_API_KEY`; no cal
   crear-ne una segona. Confirmar amb la documentació del servei si suporta aquest
   header, limitar-la a `personal.connectapi.garmin.com` i introduir el valor només
   al camp segur quan s'hagi autoritzat. No incloure'l a l'ordre de setup.
3. Revisar l'accés a Internet de l'entorn: host Personal API per runtime; PyPI i
   files.pythonhosted.org per instal·lació, i developer.garmin.com només si cal
   descarregar documentació. No s'han modificat les regles existents en aquesta tasca.
4. Desar/aplicar la configuració amb el flux de revisió del servei i reiniciar
   l'entorn si ho requereix. Reconsultar `environment_status`: cal observació actual
   i secret `ready`, i política `enforced`; els estats `unknown` no són suficients.
5. Completar `docs/API_CONTRACT.md`. L'agent podrà fer la prova autenticada petita
   només després de la teva aprovació explícita d'aquest mecanisme. No activarem
   automàticament tota la descàrrega històrica com a prova inicial.

Els noms i posició dels menús poden variar segons la versió de Codex Web. Si el
servei no ofereix la vinculació segura descrita, cal aturar la configuració; no
substituir-la per una clau en fitxers, Git, setup, PowerShell o ordres compartides.

## Persistència i operació

La CLI crea dades amb umask 077; els originals s'escriuen atòmicament amb permisos
600, i la DB SQLite també té permisos 600. Això no és xifratge. El volum ha de ser
privat i xifrat pel sistema on es conservin dades reals. Còpies de seguretat també
privades. El contenidor Codex no és emmagatzematge permanent.

No s'ha configurat execució periòdica ni infraestructura. Proposta per a fase 5:
servei privat amb volum xifrat persistent o PostgreSQL privat + emmagatzematge
privat d'originals, gestor de secrets, un únic sincronitzador programat, còpies de
seguretat i autenticació del dashboard. Cal triar proveïdor i costos abans d'implementar.
