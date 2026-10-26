# Arquitectura definitiva: Windows local, versió 0.2

Decisió de l'usuari: 0 € d'infraestructura recurrent, sense cloud, servidors de pagament
ni bases de dades externes. Les alternatives cloud de revisions anteriors queden
substituïdes; no s'ha desplegat cap infraestructura ni es proposa contractar-ne cap.

## Distribució i inici

`windows/Install.ps1` i els accessos `.cmd` instal·len Python 3.12 de 64 bits i un venv
propi per versió. La instal·lació crea un accés directe, no requereix copiar codi ni
executar PowerShell manualment. `Actualitzar.cmd` reutilitza el mateix procediment:
venv nou, comprovació de diagnòstic i canvi d'accés directe només després d'èxit.
Les dades viuen fora del directori de programa i no s'esborren en actualitzar.

`desktop.launcher` imposa `127.0.0.1`, headless, CORS/XSRF i usage stats desactivades;
obre el navegador quan el servidor local està preparat. Un lock d'app reutilitza la
sessió ja iniciada; una comprovació de port evita obrir accidentalment un altre servidor.
Cap listen a 0.0.0.0 ni hosting extern. El navegador no envia activitats a Plotly Cloud.
No hi ha actualització automàtica de codi a l'inici: la consulta segueix funcionant offline.

PyInstaller/.exe independent queda per una etapa posterior després de validar aquest
paquet; no se'n distribueix cap binari ni s'afirma compatibilitat provada.

## Capes reutilitzades i afegides

- `fit`, `ingestion`, `garmin`, `storage`: motor existent, amb originals immutables,
  versionat, paginació auditada, staging i recuperació.
- `desktop/local.py`: rutes, preferències atòmiques sense secrets i logging rotatiu.
- `desktop/credentials.py`: WinVaultKeyring explícit; cap fallback a text pla o entorn.
- `desktop/controller.py`: worker, consentiment, lock d'escriptor, progrés i cancel·lació.
- `desktop/app.py` i `views.py`: Streamlit en català, consultes i gràfics locals.
- `physiology/friel.py`, `vdot/vdot_engine.py`: càlculs versionats amb fonts i límits
  a METHODS.md. No s'estima cap indicador personal de dades no confirmades.

## Persistència local i rendiment

`%LOCALAPPDATA%\GarminRunningAnalytics\`: analytics.sqlite3, originals/, imports/,
staging/, backups/, logs/, settings.json i sync-status.json. Rutes configurables a
launcher `--data-dir` o GRA_DATA_DIR; usar disc local i evitar carpetes sincronitzades
amb núvol. No executar SQLite sobre un filesystem remot.

Esquema 2: s'afegeix `activity_index` amb data, esport, mètriques, flags i dispositiu,
sense samples/missatges. Actualitzat dins del mateix commit que l'activitat. La
migració 1→2 crea una còpia SQLite abans de canviar res i indexa una activitat cada
vegada. No es modifiquen originals ni activitats existents. Esquemes aliens o futurs
es rebutgen. Un rollback de programa antic requereix restaurar el backup d'esquema 1.

Inici: només índex lleuger, no FIT originals ni tots els registres de la DB. Historial
filtrat/paginat amb SQL. Resum setmanal/mensual amb mètriques lleugeres i cache invalidada
quan acaba un job. Detall sota demanda, cache per ID i versió de l'activitat, dos detalls
com a màxim. Les activitats no modificades no tornen a ser parsejades per sincronitzar.
Un test usa 2.000 activitats i comprova que les consultes de resums no seleccionen el
payload de samples. No és encara un benchmark de RAM/latència en un PC amb historial real.

Importació d'un directori: límit de seguretat per cada FIT/contenidor, no per tot el
volum històric. ZIP continua limitat a 512 MiB acumulats, 128 MiB per entrada, quatre
nivells i 10.000 entrades per contenidor; exports més grans: descomprimir localment i
importar directori. Les rutes ZIP no s'extreuen al filesystem. Multisessió FIT segueix
rebutjada explícitament en comptes de fusionar esports o perdre transicions.

## Consentiment i sincronització en obrir

L'app consulta i renderitza l'històric abans de programar xarxa. Un controlador amb
cache per procés marca un únic intent automàtic; els reruns/fragments no n'inicien
més. Tancar només la pestanya manté el procés: no és un nou inici d'app. El botó manual
permet reintentar. `threading.Lock` protegeix estat i FileLock amb context compartit
entre fils impedeix escriptors simultanis, també entre processos. Imports i backups
usen el mateix lock. La CLI avançada no s'ha d'executar com a segon escriptor alhora.

Autorització inicial explícita + credencial configurada + contracte validat. La
constant OFFICIAL_CONTRACT_VALIDATED continua False perquè manca l'OAS complet;
no és editable des d'un checkbox. També bloqueja la CLI abans de llegir credencials.
No s'han fet peticions reals. Les proves injecten un transport simulat i valors ficticis.

Quan s'habiliti legítimament, la cerca oficial servirà de comprovació de connectivitat.
Worker daemon separat, sense ordres Streamlit dins del fil. La GUI sondeja estat amb
fragment cada dos segons i refresca quan canvia la revisió. Mostra connexió, pàgines,
noves/actualitzades, errors i últim èxit UTC. No coneix el total abans de paginar i no
mostra un percentatge d'avanç inventat. En fallar hi ha accés permanent a la DB local.

Cancel·lació cooperativa entre peticions/preparació/commit; no aborta a mig commit.
La petició activa pot trigar fins al seu timeout. Ctrl+C o tancar el procés pot
interrompre una pàgina; staging i checkpoint es recuperen al proper inici.

## Protocol de consistència i auditoria

HTTP, parsing CRC, arxiu ZIP/FIT, detall/resum/payload i manifests privats SHA-256 fora
de SQL. Després es valida staging i s'obre una transacció curta: activitats, versions,
índex i checkpoint es comprometen conjuntament. Un error desfà tota la pàgina.
Sense manifest complet: es torna a descarregar; manifest corrupte: aturar i conservar.
No hi ha atomicitat distribuïda filesystem/SQL; poden quedar originals orfes, però
no s'eliminen ni s'escriu una referència SQL abans que existeixi l'original.

La represa reinicia offset zero reutilitzant staging del mateix run. Registra IDs,
hashes, offsets i intents; duplicats exactes només es processen una vegada i conflictes
aturen la pàgina. Segona passada de catàleg, sense FIT, compara IDs/seqüència/signatures.
Discrepàncies són possibles omissions/altes/baixes, no prova d'eliminació remota. No
s'usen salts d'IDs globals per inferir buits. Una reconciliació incompleta/canviant és
unstable; exhausted no certifica exhaustivitat. La cobertura sempre no verificada.
resume_log i reconciliation_history preserven la informació dels intents anteriors.

## Secrets i seguretat

Clau exclusivament Windows Credential Manager amb WinVaultKeyring. No fallback a
backend de text, no lectura d'API Key de l'entorn, ni còpia de Codex Cloud. Tokens només
en memòria. Preferències/estat no contenen secrets; logs són codis genèrics, sense
str(exc), traceback, cossos HTTP, headers ni URLs amb credencials. Windows ACL del
perfil i BitLocker/xifratge del dispositiu protegeixen dades en repòs; SQLite i FIT
no estan xifrats per l'app. Vegeu SECURITY.md.

## Backups, restauració i actualitzacions

Botó local: worker adquireix el lock, SQLite backup API i còpia d'originals, imports,
staging, settings i estat. No inclou Credential Manager ni fitxers de lock. No recorre
backups/ dins d'una altra còpia. Recomanació: còpia després de cada importació i segona
còpia manual a USB xifrat. Cap transferència a proveïdors. Restauració: app tancada,
conservar carpeta actual i substituir-la per contingut del backup, validar recomptes,
versions i hashes. Les proves restauren dades sintètiques, no certifiquen el disc físic.

Actualitzar no canvia LOCALAPPDATA de dades, no esborra originals i conserva el venv
anterior. No hi ha servei permanent de Windows ni tasca programada instal·lada:
només s'executa quan l'usuari obre l'app.
