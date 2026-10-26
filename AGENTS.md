# Convencions
Python >=3.12, src/garmin_running, tipus explícits, responsabilitats separades.
Idioma de documentació i CLI: català. Unitats mètriques; UTC per a instants,
zona horària desconeguda explícita. Mai inferir LTHR de FC màxima ni VDOT de VO₂max.
No fer peticions autenticades fins a aprovació explícita del mecanisme de secrets.
No llegir ni imprimir secrets. No incorporar dades personals, FIT, DB ni ubicacions a Git.
No inventar endpoints ni declarar completa una cobertura sense contrast extern.
Proves amb fixtures sintètiques i httpx.MockTransport, sense credencials ni xarxa.
Validació: `python -m pytest -q`, `ruff check .`, `ruff format --check .`.
No publicar dashboards ni configurar execució persistent en aquesta fase.
