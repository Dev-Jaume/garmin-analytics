"""CLI offline per defecte. Cap lectura de credencials en importació o auditoria."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from garmin_running.garmin.client import OFFICIAL_CONTRACT_VALIDATED, GarminClient
from garmin_running.garmin.sync import Synchronizer
from garmin_running.ingestion.importer import Importer
from garmin_running.storage.repository import Repository


def main() -> int:
    parser = argparse.ArgumentParser(description="Garmin Running Analytics — fase 1")
    parser.add_argument("--data-dir", type=Path, default=Path("private"))
    parser.add_argument("--database-url", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Crea persistència privada local")
    imp = commands.add_parser("import", help="Importa FIT, directori o ZIP d'exportació")
    imp.add_argument("path", type=Path)
    imp.add_argument("--activity-id", help="ID Garmin verificat per a un únic FIT")
    commands.add_parser("coverage", help="Audita dates, pàgines i limitacions")
    sync = commands.add_parser("sync", help="Bloquejat fins a revisió de secrets i contracte")
    sync.add_argument("--secrets-approved", action="store_true")
    sync.add_argument("--contract-verified", action="store_true")
    sync.add_argument("--resume")
    sync.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.command == "sync" and not (args.secrets_approved and args.contract_verified):
        parser.error("Cal revisar docs/SECURITY.md i docs/API_CONTRACT.md abans d'habilitar sync")
    if args.command == "sync" and not OFFICIAL_CONTRACT_VALIDATED:
        parser.error("Connexió bloquejada: contracte oficial complet pendent de validar")
    # El directori i la DB s'han de situar en volum privat per a dades reals.
    os.umask(0o077)
    args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    repo = Repository(
        args.database_url or f"sqlite:///{args.data_dir / 'analytics.sqlite3'}", args.data_dir
    )
    try:
        if args.command == "import":
            report = Importer(repo).import_path(args.path, args.activity_id)
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 1 if report.errors else 0
        if args.command == "coverage":
            print(json.dumps(repo.coverage(), ensure_ascii=False, indent=2))
        elif args.command == "init":
            print("Persistència inicialitzada; encara no hi ha dades personals importades.")
        elif args.command == "sync":
            from garmin_running.desktop.credentials import WindowsCredentials

            client = GarminClient(
                WindowsCredentials().get() or "", approved=True, contract_verified=True
            )
            try:
                run_id = Synchronizer(client, repo).run(resume=args.resume, refresh=args.refresh)
                print(json.dumps({"run_id": run_id, "coverage": "Cobertura no verificada"}))
            finally:
                client.close()
    finally:
        repo.engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
