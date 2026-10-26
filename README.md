# Garmin Running Analytics — Windows local

Aplicació personal Python + Streamlit en català, executable des d'un accés directe.
**0 € d'infraestructura recurrent**, sense hosting, servidors de pagament ni DB externa.
Reutilitza el motor d'importació i sincronització de la PR #1.

## Instal·lació a Windows

1. Descarrega el [ZIP de la branca de la PR](https://github.com/Dev-Jaume/garmin-analytics/archive/refs/heads/codex/phase1-ingestion.zip).
2. Descomprimeix-lo i obre `windows/Instal·lar.cmd` amb doble clic.
3. El programa prepara Python 3.12/entorn propi i crea **Garmin Running Analytics** a l'escriptori.
4. Obre l'accés directe. El navegador s'obre a `http://127.0.0.1:8501`.
5. A **Configuració**, importa FIT/ZIP/directori local i consulta l'historial offline.

[Instruccions completes d'instal·lació, ús i actualització](docs/WINDOWS.md).
La instal·lació inicial necessita Internet per descarregar Python/dependències; després
la consulta i importació funcionen offline. No és encara un .exe independent.

## Dades i seguretat

Dades a `%LOCALAPPDATA%\GarminRunningAnalytics\`: SQLite, originals, imports, staging,
backups i logs. Programes a `%LOCALAPPDATA%\Programs\GarminRunningAnalytics\`, separats de les dades.
L'actualització crea un entorn nou i preserva l'historial. Còpies locals des de la GUI.

Clau només a Windows Credential Manager; no a fitxers, SQLite, logs ni Git.
No es llegeix ni copia cap clau de Codex Cloud. Streamlit només escolta a loopback,
amb CORS/XSRF i telemetria desactivada. No es publiquen dades ni gràfics a serveis externs.

## Sincronització

Worker en segon pla; històric local disponible durant xarxa, lock entre processos,
progrés i botons de sincronització/interrupció. Una única sincronització automàtica
per inici de procés, sense repeticions pels reruns. Requereix consentiment explícit.
La cerca oficial comprova connexió i reconcilia tot el catàleg; no assumeix un endpoint
que retorni només novetats. Descàrregues, staging i parsing fora de SQL; commit de pàgina
amb checkpoint, represa des de zero i reutilització de staging íntegre.

**La connexió Garmin real continua bloquejada** fins a completar la verificació del
contracte oficial. La versió actual és funcional offline i té el mecanisme de worker
provat amb mocks; no s'ha validat ni executat la sincronització contra un compte real.
Desar una clau o marcar consentiment no salta el bloqueig del contracte.

## Dashboard

- Resum de volum setmanal/mensual, hores, ritme ponderat i activitats recents.
- Historial filtrable i paginat; detall de FC, ritme, cadència, altitud, voltes i pauses.
- Friel clàssic: LTHR manual validat i versionat, zones, temps per zona i indicadors òptics.
- VDOT Daniels–Gilbert de rendiments confirmats i recents, equivalents i històric.
- E/M/T/I/R com a **estimacions orientatives del model**, activades expressament;
  sense afirmar coincidència amb les taules oficials. [Mètodes i limitacions](docs/METHODS.md).
- Qualitat i auditoria: cobertura no verificada, flags i discrepàncies de paginació.

No hi ha dades fictícies preinstal·lades. Sense fonts validades, els indicadors personals
es mostren com a no determinats. Índex lleuger de resums: no es carreguen tots els
registres FIT a l'inici; detall i càlculs només de l'activitat seleccionada, amb cache.

## Desenvolupament amb Codex i GitHub

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

A Windows, Python de l'entorn és `.venv\Scripts\python.exe`. L'usuari final no necessita
executar aquestes ordres: usa l'instal·lador. La CI inclou Windows i Linux, AppTest,
credencials sintètiques i instal·lació Windows sense iniciar navegador. GitHub conserva
només codi/fixtures. Cap dada real s'ha de copiar a Codex ni publicar a la PR.

- [Arquitectura local](docs/ARCHITECTURE.md)
- [Contracte Garmin i aspectes pendents](docs/API_CONTRACT.md)
- [Seguretat](docs/SECURITY.md)
- [Informe de versió](docs/PHASE1_REPORT.md)
- [Validació](docs/VALIDATION.md)
