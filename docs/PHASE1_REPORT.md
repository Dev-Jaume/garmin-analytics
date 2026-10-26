# Revisió de tancament de fase 1 — 26 d'octubre de 2026

## Estat funcional i contracte

Importació offline implementada amb Python 3.12, SQLAlchemy, SQLite i fitdecode.
Es conserven originals, versions, registres, pauses, unitats i errors d'importació.
Client i sincronitzador paginat provats només amb transport simulat.

Les FAQ oficials confirmen generació OAuth2 amb Authorization: ApiKey i absència
de refresh tokens. El client renova mitjançant una nova petició de token; una prova
comprova també que ignora un refresh_token hipotètic retornat pel mock.

El Swagger complet continua inaccessible: rebuig CONNECT 403 del proxy, no resposta
403 de Garmin. No s'ha eludit el bloqueig. Rutes visibles a l'índex, però paràmetres,
esquemes i capçalera de recursos encara provisionals. Detall a `API_CONTRACT.md`.

## Canvis sorgits de la revisió

- Validació de versió abans de crear taules; DB alienes/incompatibles queden intactes.
- Rebuig de caducitat booleana del token.
- Xarxa real prohibida a tota la suite; execució sense GARMIN_API_KEY heretada.
- Proves explícites de no ús de refresh tokens i backup/restauració conjunta.
- Exclusió Git ampliada per formats FIT/ubicacions i fitxers de claus.
- CI preparada per instal·lar el lock auditat i la versió local sense canviar dependències.

## Resultats i privacitat

55 proves superades; Ruff correcte; smoke idempotent i pip check correctes.
pip-audit: 15 dependències, cap vulnerabilitat coneguda. Bandit: 3 avisos baixos
revisats (ruta pública i jitter), cap mitjà/alt. Vegeu `VALIDATION.md`.

Revisats els 31 fitxers candidats a publicació: sense credencials reals, dades de
salut, FIT reals, ubicacions ni DB privades detectades. Només fixtures sintètiques.
Cap petició autenticada a Garmin, cap desplegament i cap fase 2 iniciada.

## Persistència

Codex Cloud és temporal. Magatzem canònic proposat: SQLite + originals en volum privat
persistent extern i xifrat. Còpies conjuntes amb escriptors aturats, SQLite backup API,
segona còpia privada i restauracions verificades amb hashes i integritat. Patró provat
amb dades sintètiques; infraestructura persistent encara no seleccionada/aprovisionada.
PostgreSQL privat futur requereix migració provada; canviar l'URL no trasllada l'historial.
Procediment complet a `ARCHITECTURE.md`.

## Preparació de Pull Request

Destí: Dev-Jaume/garmin-analytics, públic i buit segons l'API GitHub. No té cap branca
base remota: no es pot obrir una PR comparant implementació contra una main inexistent.

S'han preparat els 31 fitxers, una base local buida i una branca d'implementació per
revisar. No s'ha inicialitzat ni escrit al repositori remot. Alternativa segura proposada:

1. Autoritzar publicar únicament el commit buit inicial com a main.
2. Publicar la branca d'implementació derivada, comprovada i sense dades privades.
3. Obrir una PR en esborrany amb proves, riscos i contracte pendent.
4. Revisar la PR abans de qualsevol merge; sense force-push ni desplegaments.

No cal introduir cap API Key per aquests passos. Inventari exacte a `FILES.md`.
