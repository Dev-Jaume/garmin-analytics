# Decisions i límits de fase 1

## Dades

Instants FIT `date_time` i camps explícitament GMT → UTC. Camps locals conserven
la representació original sense assignar una zona horària inventada. La zona
IANA de l'activitat és `null` si no està disponible. No es deriva de coordenades.

Mètriques FIT escalades: metres, segons, m/s, BPM. Ritme mitjà = temps de timer /
distància × 1000; s'indica la base temporal i no s'atribueix a temps en moviment.
El temps en moviment es deixa absent si el FIT no el proporciona. Velocitat màxima
és una lectura sense validar, mai un ritme de rendiment fiable. Cadència es conserva
en unitat original; no es multiplica per dos sense validar semàntica del dispositiu.

Els registres conserven ordre, duplicats, absències, mostreig irregular i esdeveniments
de timer. No es calcula temps per zona en aquesta fase ni s'interpola a través de
pauses/buits. FC màxima observada és una mesura separada de qualsevol llindar futur.

Tots els missatges FIT inclouen camps, unitats i raw_value del parser. El FIT immutable
és l'autoritat per recuperar bytes originals; fitdecode pot aplicar escala als raw_value
d'alguns components expandits. No s'afirma que aquests camps siguin un bolcat binari.

## Persistència

SQLAlchemy Core desacobla SQL i ingesta. SQLite s'ha provat realment. L'URL admet
PostgreSQL mitjançant l'extra `postgres`, però la migració, el driver i les proves de
producció PostgreSQL encara estan pendents. No s'afirma compatibilitat validada.

Activitats, àlies, versions (hash de FIT + payload), registres d'importació i execucions
de sincronització tenen taules separades. Registres/voltes/missatges es guarden en JSON
per activitat: simplifica la traçabilitat inicial, però no és una taula de sèries temporals
indexada per consultes massives. Abans del dashboard cal mesurar memòria i rendiment
amb historial real i valorar taules/Parquet privats per registres.

Esquema versionat 1; versions desconegudes es rebutgen. No hi ha migrador automàtic.
Un sol escriptor simultani suportat. Les pàgines són transaccionals, però les peticions
HTTP es fan dins de la transacció: no executar altres escriptors durant sincronització.
Fitxers originals orfes després d'una fallada són segurs; no s'eliminen automàticament.

## Límits operatius explícits

Importació: 512 MiB acumulats per execució, 128 MiB per entrada ZIP/FIT, 10.000 entrades,
4 nivells ZIP, configurables a `Importer`. Per exportacions més grans, importar parts
per separat o ajustar límits en una futura opció CLI després d'avaluar memòria.
La suma inclou contenidors comprimits i entrades descomprimides. Mai extreure rutes ZIP.

Client: timeout 30 s per operació HTTP, 3 reintents addicionals, interval mínim 1 s
configurable, resposta JSON màxima 16 MiB i descàrrega 128 MiB. Són límits locals
prudents, **no quotes oficials de Garmin**. Retry-After superior a 60 s ajorna l'operació
perquè es pugui reprendre més tard. No hi ha timeout total d'una execució ni scheduler.

El catàleg es torna a consultar completament; només les descàrregues són incrementals.
Això evita tallar la cerca només perquè apareix una activitat ja coneguda. Modificacions
no reflectides al resum requereixen `--refresh`. Ni offsets solapats ni pàgina buida
proven exhaustivitat. No es filtren esports a origen: es conserva l'historial recuperat;
`ActivityData.is_running` permet identificar running per a fases posteriors.

No hi ha encara: control de qualitat fisiològica de FC, LTHR, zones Friel, VDOT, ritmes,
dashboard Streamlit, autenticació de dashboard ni automatització permanent. Són les
fases següents, no valors ficticis ni estimacions incompletes presentades com a vàlides.

## Conservació de l'historial fora de Codex Cloud

Per a la fase 1, el magatzem canònic serà SQLite + `originals/` en un volum privat
persistent extern a Codex (ordinador/servidor/NAS privat amb disc xifrat). El codi es
versiona a GitHub; DB, FIT, exportacions i backups mai. No s'ha seleccionat ni
aprovisionat cap proveïdor, ni s'ha transferit cap dada real en aquesta revisió.

Procediment de conservació, abans de qualsevol importació real a Codex:

1. Designar el volum extern privat i el responsable de còpia/restauració. Si no està
   disponible, no considerar segura la conservació d'un historial real al contenidor.
2. Executar la CLI al sistema persistent, amb `--data-dir /volum/privat/garmin` i
   `--database-url sqlite:////volum/privat/garmin/analytics.sqlite3`. Si es treballa a
   Codex, el volum o mecanisme privat de transferència s'ha de configurar i validar
   abans; no hi ha cap muntatge persistent implícit ni sincronització automàtica.
3. Fer còpies conjuntes amb els escriptors aturats: SQLite mitjançant l'API `backup`
   de sqlite3, i tot `originals/`. Incloure també inventaris i checkpoints dins la DB.
   No copiar simplement una DB activa amb `cp`: podria ometre informació del journal/WAL.
4. Guardar la còpia completa en una segona ubicació privada, xifrada i independent.
   Conservar versions anteriors i la clau de xifratge fora de Git i del mateix backup.
5. Abans de destruir l'entorn temporal, restaurar la còpia en un directori net;
   comprovar `PRAGMA integrity_check`, SHA-256 de tots els originals, recompte
   d'activitats, versions, àlies, checkpoints i dates extremes. No eliminar l'origen
   fins que la restauració s'hagi verificat.
6. Validar restauracions periòdicament. Objectiu proposat: còpia després de cada
   importació/sincronització, 7 versions diàries i 4 setmanals; pendent d'acord amb
   capacitat i política de privacitat, encara sense scheduler implementat.

La suite ha provat aquest patró de backup/restauració amb SQLite i dos FIT sintètics
versionats. No certifica la durabilitat d'un proveïdor extern encara no configurat.
La creació del repositori comprova la versió abans de modificar una DB existent;
DB alienes o incompatibles es rebutgen sense afegir-hi taules.

En una fase posterior, PostgreSQL privat substituiria SQLite per a concurrència i
operació continuada; els FIT seguirien en emmagatzematge privat versionat, amb claus
per hash i camins relatius. Cal una migració verificada (IDs, recomptes, versions,
JSON i hashes) i pla de retorn abans del canvi. Canviar només l'URL no migra dades.
