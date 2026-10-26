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
Un sol sincronitzador escriptor suportat. Les peticions HTTP, parsing FIT i staging
es fan fora de transaccions SQL; el commit d'una pàgina inclou activitats i checkpoint.
Els originals orfes després d'una fallada es conserven per a auditoria.

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
no reflectides al resum requereixen `--refresh`. Ni dues passades estables ni pàgina buida
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
   de sqlite3, i tot `originals/` i `staging/`. Incloure també inventaris i checkpoints dins la DB.
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

## Protocol de sincronització i recuperació

1. Llegir estat i àlies en una transacció curta i tancar-la abans de fer HTTP.
2. Cercar una pàgina i comprovar IDs, duplicats exactes/conflictius i empremta de pàgina.
3. Per a cada activitat modificada: HTTP de detall i ZIP, arxiu immutable del ZIP/FIT,
   parsing CRC, metadades i payload normalitzat. Tot fora de SQL. El manifest privat
   `staging/<run_uuid>/<id>-<summary_sha>.json` s'escriu atòmicament amb fsync.
4. Revalidar hashes del manifest i dels originals. Un staging íntegre de la mateixa
   execució es reutilitza; corrupció o absència d'un original atura la represa.
5. Obrir una transacció SQL curta: `save_archived` escriu només SQL, després actualitzar
   el checkpoint amb comprovació optimista del número de pàgina. Fer commit conjunt.
   Si falla qualsevol activitat o checkpoint, tota la pàgina es desfà.
6. Fer una segona passada de cerca, sense FIT ni SQL obert durant HTTP, i comparar el
   catàleg observat. Guardar-ne el resultat en una altra transacció curta.

Staging i originals són dades privades, ignorades per Git i sota permisos de fitxer
600/directori 700 quan es creen. No contenen tokens. Es conserven també el detall,
resum i payload en l'arxiu per hash. No es netegen automàticament: cal validar abans
una política de retenció per evitar pèrdues. El volum s'ha de xifrar; permisos i hashes
no són xifratge. El staging pot augmentar l'espai utilitzat considerablement.

Una fallada de xarxa o disc abans de completar el manifest pot deixar originals
orfes; en reprendre es torna a descarregar aquella activitat. Si el manifest és
complet, no cal baixar-la de nou. Una fallada SQL deixa staging reutilitzable i el
checkpoint anterior. KeyboardInterrupt es registra com `interrupted`; un SIGKILL
pot deixar `running`, però el staging i l'últim checkpoint compromès permeten reprendre.
El protocol està provat amb excepcions injectades, no amb talls físics d'alimentació.
No hi ha atomicitat distribuïda entre filesystem i SQL: s'escriu primer al filesystem,
no s'eliminen originals i així una fallada de procés deixa orfes, no referències noves
compromeses a originals encara no escrits. Corrupció posterior del disc requereix backup.

La represa torna a l'offset zero per evitar omissions per desplaçaments acumulats;
es conserven les versions i signatures compromeses i es reutilitza staging íntegre.
No es reutilitza staging entre execucions noves. Esquema SQL 1 sense migració: només
s'afegeixen camps versionats `audit_version=2` al JSON d'auditoria.

## Auditoria de paginació ampliada

Cada pàgina compromesa registra intent, offset, IDs, nombre d'entrades, hash i hora.
La pàgina pendent es conserva a l'auditoria si una preparació falla; en reprendre,
resume_log i reconciliation_history preserven els intents/lectures anteriors. S'etiqueten
IDs repetits dins/entre pàgines, resums conflictius o canviats i pàgines repetides.
Duplicats idèntics es processen una vegada; els conflictius aturen la pàgina.

La reconciliació registra pàgines/IDs, nous IDs no vistos a la primera passada, IDs
que no reapareixen, resums modificats, ordre diferent i IDs coneguts de la DB que ja
no es veuen. Són discrepàncies candidates: poden ser omissions, altes, baixes o canvis
d'ordenació; no són proves de supressió remota ni motiu per esborrar dades locals.
Els IDs són globals i no se'n pressuposa contigüitat numèrica. Intervals temporals
sense activitats es continuen mostrant a `coverage`, amb la política documentada.

`exhausted` significa que s'ha observat pàgina buida a dues passades i sense incidències;
`unstable` indica discrepàncies o reconciliació incompleta; `page_limit`, `failed` i
`interrupted` requereixen revisió/represa. Cap estat significa historial complet.
Una modificació que no aparegui a cap de les dues lectures o no canviï el resum pot
passar desapercebuda: cal inventari extern i `--refresh` periòdic. La reconciliació
no descarrega automàticament els IDs nous; es recuperen en una nova passada.
Cada passada té el pressupost `max_pages`; el cost de cerca pot arribar a 2× aquest
límit, a més dels detalls i FIT. Cal confirmar quotes oficials abans d'operació real.

## Dues opcions concretes de persistència permanent

Propostes, **sense desplegament ni contractació**. Pressupostos consultats el
26-10-2026, USD/mes sense impostos, dins quotes incloses, amb fins a 20 GiB totals de
fitxers (inclosos staging/còpies actives). En B es pressuposta el node mínim de DB
i una reserva opcional de 10 GiB addicionals. Costos de
manteniment humà, dominis, serveis VPN de pagament, excés d'espai/transferència i
còpies independents addicionals no inclosos. No és una oferta comercial garantida.

| | A — SQLite en Droplet privat | B — PostgreSQL gestionat privat + worker |
| --- | --- | --- |
| Proveïdor/configuració | DigitalOcean, regió UE, Droplet Basic 2 GiB, volum 20 GiB LUKS | DigitalOcean, PostgreSQL Basic 1 GiB, worker Basic 2 GiB i volum LUKS 20 GiB per originals/staging |
| Originals i backup | Filesystem del volum; restic amb xifratge de client a Spaces privat, CDN desactivada | Originals/staging al volum del worker; backup restic a Spaces; backup/PITR del servei DB i exportacions coordinades |
| Privacitat | CLI només al worker, un escriptor; accés privat per VPN/SSH autoritzat | DB en VPC, trusted sources limitades al worker; connexió TLS `verify-full`, rol mínim |
| Xifratge | LUKS amb clau fora de Git/root disc, swap desactivat o xifrat; restic xifrat abans de sortir | DB xifrada en repòs pel servei i TLS; LUKS per filesystem i restic per backup |
| Cost base calculat | worker $12 + volum $2 + Spaces $5 = **$19/mes** | worker $12 + volum $2 + PostgreSQL $15.15 + Spaces $5 = **$34.15/mes**; reserva de 10 GiB addicionals $2.15 → **$36.30/mes** |
| Pressupost operatiu orientatiu | **$19–25/mes**; unes 1–2 h/mes d'administració pròpia | **$35–45/mes**; unes 0.5–1.5 h/mes, sobretot worker/backup |
| Avantatges | Compatible directament amb la persistència provada, baixa complexitat i cost | DB gestionada, millor concurrència i recuperació; separa el cicle de vida del worker de la DB |
| Inconvenients | Pedaços del SO, desbloqueig LUKS, còpies/restauració a càrrec nostre; sense alta disponibilitat | Migració SQLite→PostgreSQL i driver pendents de prova; FIT encara depenen del volum/backup; més cost i coordinació DB/filesystem |

Fonts oficials de preus: [Droplets](https://www.digitalocean.com/pricing/droplets),
[Volumes](https://docs.digitalocean.com/products/volumes/details/pricing/),
[Spaces](https://www.digitalocean.com/pricing/spaces-object-storage),
[PostgreSQL](https://www.digitalocean.com/pricing/managed-databases) i
[emmagatzematge addicional PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/).
Seguretat DB: [documentació oficial](https://docs.digitalocean.com/products/databases/postgresql/how-to/secure/).
Els càlculs són estimacions pròpies sobre aquestes tarifes; verificar pressupost
final, regió i impostos abans d'autoritzar. El clúster mínim no és alta disponibilitat.

Compatibilitat amb Codex Web en ambdues: Codex manté només codi i fixtures sintètiques;
el worker persistent és l'autoritat de les dades. Accés operatiu només amb VPN/TCP
explicitament configurats i aprovats al runtime, respectant el proxy, allowlists i
gestor de secrets. Ara no hi ha cap connexió configurada a aquests serveis. No cal
copiar l'historial real al contenidor per desenvolupar. SQLite s'executa al worker,
mai s'obre com a fitxer compartit per NFS/SSHFS des de Codex. En l'opció B la DB no
s'exposa públicament per facilitar Codex. La publicació de codi des de la PR i les
operacions remotes també necessiten el flux d'autorització corresponent.

Recomanació inicial: opció A per a ús personal d'un sol escriptor. Passar a B quan
hi hagi necessitat real de concurrència, després d'una migració i restauració
verificades. Ni muntatges, ni buckets, ni VPN, ni scheduler s'han creat en aquesta tasca.
