# Validació Windows local 0.2 — 26 d'octubre de 2026

## Resultats locals verificats

Python 3.12.14. Dependències universals a requirements-desktop.lock, inclosos marcadors
Windows/Linux. Les proves retiren GARMIN_API_KEY i prohibeixen xarxa real amb fixture
autouse; només dades, claus i transports sintètics.

| Comprovació executada | Resultat |
| --- | --- |
| pytest complet | **114 passed, 1 skipped in 35.31s** |
| Ruff check i format | Correctes |
| pip check | Cap dependència trencada |
| AppTest | Totes les pàgines, historial buit/importat i estimacions opcionals, sense Internet |
| Servidor Streamlit real | Health HTTP 200; listener comprovat només 127.0.0.1:18765 |
| pip-audit dels pins del lock, sense filtrar per plataforma | **58 versions auditades, 0 vulnerabilitats conegudes** |
| Bandit | **5 LOW**, 0 MEDIUM/HIGH, revisats sense supressions |
| Revisió de candidats a Git | Sense credencials reals, FIT, DB o dades personals detectades |

L'únic skip local és el round-trip natiu de Windows Credential Manager. A Windows
la prova crea i elimina una entrada **sintètica en un servei únic de tests**, mai al
servei real de l'app. L'estat Windows real es comprova als checks de GitHub, no s'infereix
d'aquesta execució Linux. No s'ha llegit cap credencial ni fet una petició a Garmin real.

## Abast de les proves

- Tota la suite anterior: FIT binaris amb CRC independent, nuls i irregularitats,
  importacions/ZIP, deduplicació/versionat, token JWT/capçaleres, backoff, idempotència,
  fallades de xarxa/disc/SQL, staging, interrupció/represa i auditoria de catàleg mutable.
- Inici offline i sense credencials; bloqueig per contracte abans de consultar clau.
- Consentiment, auto-sync única encara que hi hagi reruns i reintent manual.
- Worker sense bloquejar lectures de la GUI; lock entre controladors/processos i
  alliberament des del fil de treball. Imports i backups comparteixen el mateix lock.
- Autenticació rebutjada i connexió interrompuda conserven l'historial local.
- Cancel·lació i revocació de consentiment, represa posterior sense duplicar descàrregues.
- Comptadors: un FIT prèviament importat que s'enriqueix per API és actualitzat, no nou.
- Windows Credential Manager explícit amb backend fictici i errors sense secret al missatge.
- Rutes Windows amb espais; preferències corruptes o consentiment de tipus incorrecte
  desactiven la xarxa; settings no admet camp API Key.
- Migració 1→2 preserva activitat, índex i originals; còpia abans de migrar.
- Backup/restauració local, sense fitxers de lock ni credencials.
- 2.000 activitats: consultes paginades de resums sense seleccionar samples; imports
  de directori amb pressupost per fitxer, no per tot l'historial.
- Valors absents no es converteixen en mesures personals zero; activitats sense data
  es poden consultar a l'historial amb filtre explícit.
- Zones Friel enteres contigües, durades amb buits/pauses i manca d'extrapolació final.
- VDOT de referència, inversió, recència sense look-ahead, unitats, bandes estimades
  E/M/T/I/R i filtres de durada/distància per intervals.
- AppTest de Resum, Historial, Detall, Friel, VDOT amb ritmes opcionals, Qualitat i
  Configuració, amb i sense dades sintètiques. No hi ha demo preinstal·lada a l'app.

## Seguretat de dependències i codi

El rang inicial filelock<4 va seleccionar 3.32.7 i pip-audit va detectar
CVE-2026-112940, CVE-2026-112913 i CVE-2026-112907. Corregit a rang >=4.2.1,<5,
lock amb **4.2.4**; s'ha repetit l'auditoria. Les 58 versions inclouen les dependències
amb marcadors Windows, auditades només com a metadades, sense instal·lar-les a Linux.
Cap dada personal ni credencial s'envia a PyPI per aquesta comprovació.

Bandit 1.9.4: B105 és TOKEN_PATH (ruta pública), dos B311 són jitter no criptogràfic,
B404/B603 són import/Popen del launcher amb llista d'arguments fixa, executable actual,
script instal·lat i port validat, sense shell. No s'han ocultat avisos; Bandit retorna
1 pels cinc LOW. No s'ha afirmat absència absoluta de risc.

Escaneig heurístic/manual de tots els fitxers versionats i nous: claus privades, tokens,
JWT literals, credencials a URL, extensions i màgia FIT/SQLite. Logs, cachés, dades de
proves i informes d'eines romanen fora de Git. Git ignora també originals/staging/
backups/settings/estat encara que algú triï accidentalment una ruta dins del repositori.

Els escaneigs no certifiquen Windows, el SO, hardware, dependències de build no fixades,
la seguretat física del PC ni fonts de dades reals. No s'ha fet cap test amb compte Garmin.

## GitHub Actions

Matriu Ubuntu + Windows amb Python 3.12, instal·lació des del lock, pytest, Ruff i
diagnòstic del launcher. A Windows: test natiu de Vault i execució de Install.ps1 amb
Windows PowerShell, sense navegador ni accessos directes al runner. El codi del
workflow no injecta secrets. Els checks de la PR són la font de l'estat remot final.

Encara no validat: winget sobre Windows personal sense Python, experiència visual
real al navegador d'aquest PC, interrupció per tall elèctric/SIGKILL físic, grans
historials reals, regressió oficial de ritmes V.O2 i contracte OAS complet. PyInstaller
no s'ha construït. El cost d'infraestructura de l'app és zero perquè tot s'executa al PC.
