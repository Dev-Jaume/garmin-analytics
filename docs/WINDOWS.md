# Instal·lar i executar la versió local Windows 0.2

Arquitectura definitiva: ordinador Windows, SQLite i fitxers locals. **0 € al mes
d'infraestructura**. No hi ha servidor cloud, base de dades externa ni subscripció.
L'ordinador i l'accés a Internet existents no estan inclosos en aquest cost.

## Instal·lació, sense escriure codi ni ordres

1. Descarrega el [ZIP de la branca de la PR #1](https://github.com/Dev-Jaume/garmin-analytics/archive/refs/heads/codex/phase1-ingestion.zip).
   No descarreguis main: encara conté només la base inicial fins que s'autoritzi el merge.
2. Descomprimeix-lo en una carpeta local. No executis el paquet dins del ZIP.
3. Obre `windows` i fes doble clic a **`Instal·lar.cmd`**.
4. El programa comprova Python 3.12 de 64 bits. Si falta i hi ha winget, proposa la
   instal·lació per al teu usuari; si no, indica instal·lar-lo des de python.org i
   repetir el doble clic. La instal·lació inicial necessita Internet per Python/PyPI.
5. Es crea un entorn Python propi, s'instal·len versions fixades i apareix l'accés
   directe **Garmin Running Analytics** a l'escriptori. No cal ser administrador.
6. S'obre el navegador a **http://127.0.0.1:8501**. El servidor escolta només aquesta
   adreça: no és accessible des d'altres ordinadors. La telemetria de Streamlit està
   desactivada; no es publiquen dades ni s'usen serveis de gràfics externs.

El paquet és un instal·lador amb scripts i Python, no un .exe independent ni un
instal·lador signat. `Instal·lar.cmd` limita l'ExecutionPolicy Bypass al procés de
configuració: no canvia la política global de Windows. Revisa el codi de la PR si
Windows et demana confirmar l'origen del fitxer. No cal desactivar l'antivirus.

## Primer ús i funcionament offline

A **Configuració**, segueix els passos de la mateixa pantalla:

1. Revisa la carpeta local de dades.
2. Importa un FIT, un ZIP Garmin o una ruta local d'exportació ja descomprimida.
   Per historials molt grans, prefereix el directori local de FIT: es processen
   individualment i no s'ha de pujar tota l'exportació al formulari del navegador.
3. Consulta Resum, Historial i Detall. Es conserva tot l'original i s'indiquen camps
   absents, anomalies i cobertura no verificada; no s'inventen activitats.
4. Opcionalment, desa la Personal API Key a **Windows Credential Manager** mitjançant
   el formulari de contrasenya. La clau no va a SQLite, settings.json, logs ni Git.
   No es copia cap clau des de Codex Cloud i desar-la no inicia una connexió.
5. L'autorització de primera connexió és una casella explícita separada. Activar
   sincronització automàtica també requereix aquest consentiment.

**Límit actual important:** la connexió real segueix bloquejada al codi perquè
l'OAS/DTO i semàntica de paginació complets encara no s'han pogut validar.
Ni desar una clau ni marcar autorització salta aquest bloqueig. No podràs descarregar
historial real automàticament en aquesta versió fins a tancar aquella validació.
La importació i consulta offline sí que funcionen. No s'ha provat cap compte real.

Quan s'autoritzi una versió amb el contracte complet validat, el mecanisme ja preparat
iniciarà una única sincronització per procés després de carregar l'historial local.
La cerca Garmin serà la comprovació de connectivitat; no es fan probes a tercers.
En fallar, es manté l'accés local. El botó **Sincronitzar ara** permetrà reintentar;
els reruns de Streamlit no tornaran a programar la mateixa sincronització automàtica.

## Ús habitual

- Doble clic a l'accés directe per obrir l'app i el navegador. Una segona obertura
  reutilitza l'aplicació ja iniciada per a la mateixa carpeta de dades.
- La finestra de servidor es queda minimitzada. Per sortir completament, restaura-la
  i tanca-la, o fes Ctrl+C. Tancar només la pestanya no atura el servidor.
- Per interrompre una sincronització, usa **Interrompre** i espera l'estat idle.
  S'atura al proper punt segur, després de la petició activa (timeout de 30 s per
  operació), sense perdre pàgines ja compromeses. La pròxima execució la reprendrà.
- El resum es refresca quan acaba el worker; la pantalla continua operativa durant
  la descàrrega/importació. S'indiquen pàgines, activitats noves/actualitzades i errors.
- Si el port 8501 està ocupat per una altra aplicació, l'inici informa de l'error;
  no s'obre automàticament aquella altra aplicació. Opció avançada: launcher `--port`.

## Dades i còpies locals

Per defecte: `%LOCALAPPDATA%\GarminRunningAnalytics\`:

- `analytics.sqlite3`: activitats, versions, índex de resums i auditoria.
- `originals/`, `imports/`, `staging/`: fitxers i preparació recuperable.
- `backups/`: còpies locals; **Crear còpia de seguretat local** treballa en segon pla
  amb el lock d'escriptor. Exporta DB + originals/staging/imports + preferències, no claus.
- `logs/`: codis d'error genèrics rotatius, sense cossos HTTP ni valors de credencials.
- `settings.json`, `sync-status.json`: preferències, consentiment, valors validats i estat;
  no contenen l'API Key.

Abans d'actualitzar una DB de l'esquema 1, es crea una còpia SQLite de seguretat.
L'esquema 2 afegeix l'índex lleuger sense esborrar activitats ni FIT. En iniciar no
es llegeixen tots els registres; només resums. Una migració antiga sí que indexa cada
activitat una vegada. No s'ha fet encara un benchmark amb un historial personal gran.

Per restaurar: tanca l'app, conserva una còpia de la carpeta actual i copia el
contingut del backup escollit a la carpeta de dades. La credencial es gestiona a
Windows Credential Manager i no forma part del backup. Recomanem una segona còpia
en un USB xifrat de la teva propietat. BitLocker/xifratge del dispositiu i ACL del
perfil Windows protegeixen les dades en repòs; l'app no xifra la DB per si mateixa.
No triïs una carpeta sincronitzada amb OneDrive/Dropbox si vols dades només al PC.

Opció avançada de rutes: `GRA_DATA_DIR` o launcher `--data-dir`, sempre en disc local.
No usar SQLite sobre NFS/SSHFS ni compartir-lo amb altres equips. Les rutes amb espais
estan admeses. Els permisos Unix no substitueixen les ACL de Windows.

## Actualitzar sense perdre l'historial

1. Atura qualsevol feina i tanca la finestra del servidor.
2. Fes una còpia local des de l'app abans de tancar-la o conserva la carpeta de dades.
3. Descarrega i descomprimeix el ZIP nou de la branca/versió revisada.
4. Fes doble clic a **`windows\Actualitzar.cmd`**.

L'actualització crea un entorn nou a `%LOCALAPPDATA%\Programs\GarminRunningAnalytics\versions\`.
Només canvia l'accés directe després d'una instal·lació correcta. La versió anterior
es conserva; no s'esborra la carpeta de dades ni originals. Les versions antigues
ocupen espai i es poden eliminar manualment quan s'hagi verificat la nova.

## Què està validat i què falta

La CI prova Python, motor, AppTest, rutes i instal·lador a Windows i Linux, sense clau
Garmin real. Els resultats remots exactes es mostren als checks de la PR. El navegador
real d'un ordinador Windows personal, la instal·lació winget en una màquina sense
Python i la sincronització contra un compte Garmin encara necessiten validació.

Friel: llindar manual validat, zones clàssiques, temps per zona i indicadors òptics;
no estimació automàtica LTHR de camp. VDOT: rendiments validats i recents, equivalents
i estimacions orientatives E/M/T/I/R, sense regressió contra taules oficials. No es
presenten com a càlculs personals validats si no s'ha confirmat la font d'entrada.

PyInstaller/.exe independent és una fase posterior: encara no es distribueix ni
s'afirma validat. Aquesta primera versió prioritza Python + Streamlit local funcional.
