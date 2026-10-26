# Garmin Running Analytics 0.2 — aplicació Windows local

Branca `codex/phase1-ingestion`, [PR #1](https://github.com/Dev-Jaume/garmin-analytics/pull/1).
Decisió definitiva de l'usuari: **0 € d'infraestructura recurrent**, sense desplegament
cloud, servidors de pagament o base de dades externa. Es reutilitza tot el motor existent.

## Primera versió lliurada

- Instal·lador per a l'usuari Windows: `windows/Instal·lar.cmd`, Python 3.12 de 64 bits,
  entorn separat i accés directe. `Actualitzar.cmd` preserva dades i versió anterior.
- Launcher local, navegador automàtic, servidor només 127.0.0.1, CORS/XSRF i telemetria
  desactivada. Un segon inici reutilitza el procés. No és encara un exe independent.
- Preferències locals, clau a Windows Credential Manager, consentiment inicial i
  sincronització automàtica opcional, sense copiar claus de Codex ni llegir-les de l'entorn.
- Worker amb lock d'escriptor entre processos, progrés, interrupció cooperativa,
  recuperació de checkpoints/staging i refresc de la GUI; reruns sense auto-sync repetit.
- Importació FIT/ZIP/directori, backup local en segon pla i dades a LOCALAPPDATA.
- Dashboard català: resum setmanal/mensual, hores i ritme ponderat, historial filtrat,
  detall de FC/ritme/cadència/altitud/voltes/pauses, qualitat i auditoria.
- Índex lleuger de resums i cache de detalls per versió. No es carreguen tots els
  registres FIT en iniciar. Test amb 2.000 activitats; falta benchmark en PC real.
- Esquema 2, còpia abans de migrar des de l'1, sense esborrar activitats ni originals.

## Indicadors i fonts

Friel clàssic running: només LTHR manual confirmat, amb data i procedència; zones sense
buits, temps reals per zona amb exclusions explícites i versió de llindar seleccionada.
Es distingeix del mètode revisat al web de Friel el 2025. Qualitat òptica descriptiva,
no probabilitat ni detecció completa d'errors. No hi ha encara estimació automàtica
LTHR de camp/retrospectiva ni zones de ritme llindar validades.

VDOT: equacions Daniels–Gilbert de rendiments confirmats amb distància/temps oficial,
font d'activitat i data. Nivell actual: resultat validat més recent dels últims 90 dies,
sense futures proves ni màxim històric antic. Equivalents i històric. E/M/T/I/R són una
derivació orientativa documentada i es mostren només amb activació explícita, etiquetats
com estimació pendent de regressió oficial. No es confonen amb VO₂max Garmin ni de laboratori.
Els formularis no preomplen LTHR o marques de competició fictícies. Vegeu METHODS.md.

## Bloqueig de Garmin real

La referència Python oficial confirma JWT en text amb exp, ApiKey/Bearer, start/limit
al SDK i ZIP; no refresh tokens. El Swagger complet continua bloquejat pel proxy i
manca validar DTO/semàntica completa. OFFICIAL_CONTRACT_VALIDATED=False bloqueja GUI
i CLI abans de llegir la clau. Ni consentiment ni credencial desada eliminen el bloqueig.
No s'ha cridat Garmin amb autenticació ni s'ha accedit a cap dada real en desenvolupar.

Per tant, **la versió és utilitzable offline**, però l'actualització automàtica des d'un
compte Garmin encara no està habilitada ni validada realment. El worker està provat
amb transports simulats. No s'ha d'anunciar com a sincronització real ja operativa.

## Validació i riscos pendents

Proves locals, AppTest de totes les pàgines, concurrència, offline, secrets ficticis,
interrupció/represa, índex i backup/restauració. Resultats exactes a VALIDATION.md i CI.
La CI inclou Windows/Linux, un round-trip sintètic de Windows Credential Manager i
execució de l'instal·lador sense obrir navegador ni crear accessos a l'escriptori del runner.
L'estat remot només es considera superat quan ho mostren els checks de la PR.
L'execució [40337284778](https://github.com/Dev-Jaume/garmin-analytics/actions/runs/40337284778)
sobre `fa5f108` ha superat Ubuntu i Windows, inclosa la instal·lació completa.
Windows: 116 proves correctes, amb Vault natiu sintètic. Local Linux: 115 correctes
i una omesa perquè requereix Windows. Cap prova ha utilitzat un compte Garmin real.

L'auditoria va detectar tres vulnerabilitats a filelock 3.32.7; s'ha actualitzat a
4.2.4 i repetit l'auditoria de les versions del lock, incloses les específiques Windows.
Els avisos baixos de Bandit es revisen i no s'oculten. No s'han incorporat FIT, DB,
claus ni dades personals al repositori. Només fixtures sintètiques.

Pendents: OAS complet i prova Garmin expressament autoritzada; prova d'experiència
visual en un Windows personal i instal·lació winget en una màquina sense Python;
benchmarks de gran historial; validació completa de sensor/LTHR i regressió de ritmes
oficials; posterior PyInstaller. No hi ha cap infraestructura contractada o desplegada,
cap merge de PR, ni publicació de dades personals.

## Instruccions exactes

[WINDOWS.md](WINDOWS.md): descarregar ZIP de la branca, descomprimir, doble clic a
`windows/Instal·lar.cmd`, obrir l'accés directe i importar des de Configuració.
No cal copiar codi, crear fitxers ni executar ordres PowerShell manualment.
