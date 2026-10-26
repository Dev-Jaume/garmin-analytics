# Seguretat de l'aplicació Windows local

Arquitectura vigent: dades només al PC de l'usuari. Sense hosting ni DB externa.
Codex Web/GitHub desenvolupen codi amb fixtures sintètiques; no conserven l'historial
personal. Les antigues instruccions de Network secrets de Codex no s'usen a l'app local.

## Credencials i consentiment

- Windows Credential Manager a través de WinVaultKeyring explícit de keyring.
- La UI no usa keyring.get_keyring amb backend triat automàticament ni fallback a fitxer.
- Clau només al formulari password i al gestor Windows; formulari es buida en enviar.
- No s'importa GARMIN_API_KEY de l'entorn ni cap secret de Codex. Desar la clau no
  contacta Garmin. Logs i SQLite no reben clau ni token.
- La primera connexió requereix consentiment separat. Auto-sync és opcional i depèn
  d'aquest consentiment; se'n pot revocar l'autorització o eliminar la credencial.
- OFFICIAL_CONTRACT_VALIDATED=False bloqueja GUI i CLI abans de consultar el gestor.
  No es pot habilitar des de preferències. Falta el contracte complet: API_CONTRACT.md.
- Proves amb clau fictícia i MockTransport; mai amb credencials o salut reals.

Quan s'habiliti una versió validada, ApiKey només al header del token oficial,
JWT/Bearer només en memòria i sense refresh token. TLS verificat, sense redireccions,
IDs positius ASCII i límits de resposta. No es persisteixen respostes del token.

## Xarxa local i privacitat

El launcher fixa listen 127.0.0.1, CORS/XSRF, headless i telemetria desactivada. Obre
el navegador local quan el servidor respon, sense exposar-lo a la LAN. L'únic bypass
del proxy és per al health check de l'adreça literal 127.0.0.1; Garmin manté TLS i la
configuració de xarxa normal del PC. No s'envia cap dada a Plotly Cloud ni a APIs d'IA.

L'aplicació no incorpora autenticació entre usuaris del mateix ordinador: qui tingui
accés a la sessió Windows o al servidor localhost obert pot consultar el dashboard.
Tanca-la i bloqueja Windows quan no l'usin. No canviïs el bind ni la publiquis.

## Fitxers i logs

Dades a LOCALAPPDATA, fora del codi/venv. settings.json conserva consentiment i dades
manuals de salut, mai secrets. Windows ACL de la carpeta del perfil són la protecció
d'accés; chmod 600 no és una ACL equivalent a Windows. Recomanat BitLocker/xifratge
del dispositiu i backups USB xifrats; l'app no xifra SQLite/FIT directament.

Logs rotatius amb codis controlats; no es desa l'excepció sencera, cos HTTP, clau,
token, nom d'activitat o localització. Els errors originals dels imports es conserven
només a l'auditoria privada. Git ignora DB, FIT, exports, staging i carpetes de dades.
No utilitzar OneDrive/Dropbox com a carpeta de dades si es vol exclusivitat al PC.

Instal·lació i actualització descarreguen programari de Python/PyPI; no envien dades
personals. Scripts no signats, venv separat per versió i sense modificació global de
política PowerShell. No hi ha telemetria, deploy automàtic, infraestructura de pagament
ni exe independent encara. La clau està protegida pel compte Windows; no queda inclosa
als backups de l'app.
