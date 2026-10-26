"""Un worker per procés i lock entre processos; cap Streamlit al fil de treball."""

import json
import threading
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from garmin_running.desktop.credentials import WindowsCredentials
from garmin_running.desktop.local import Preferences, atomic_json, event_logger
from garmin_running.garmin.client import OFFICIAL_CONTRACT_VALIDATED, GarminClient, GarminError
from garmin_running.garmin.sync import SyncCancelled, Synchronizer
from garmin_running.ingestion.importer import Importer
from garmin_running.storage.repository import Repository

# No pot habilitar-se des d'un checkbox. Vegeu API_CONTRACT.md.
CONTRACT_VALIDATED = OFFICIAL_CONTRACT_VALIDATED


@dataclass
class JobState:
    phase: str = "idle"
    connection: str = "No comprovada"
    message: str = "Historial local disponible"
    pages: int = 0
    new: int = 0
    updated: int = 0
    errors: int = 0
    last_sync: str | None = None
    run_id: str | None = None
    revision: int = 0
    outcome: str | None = None


class DesktopController:
    def __init__(
        self,
        paths,
        *,
        credentials=None,
        client_factory=GarminClient,
        contract_validated=CONTRACT_VALIDATED,
    ):
        self.paths = paths.ensure()
        self.preferences = Preferences(paths)
        self.credentials = credentials or WindowsCredentials()
        self.client_factory = client_factory
        self.contract_validated = contract_validated
        self._mutex = threading.Lock()
        self._writer = FileLock(str(paths.root / "writer.lock"), timeout=0, thread_local=False)
        self._cancel = threading.Event()
        self._automatic_attempted = False
        self.thread = None
        self.logger = event_logger(paths)
        self.state = JobState()
        status = paths.root / "sync-status.json"
        if status.exists():
            try:
                saved = json.loads(status.read_text(encoding="utf-8"))
                self.state.last_sync, self.state.run_id = (
                    saved.get("last_sync"),
                    saved.get("run_id"),
                )
            except (ValueError, OSError):
                self.logger.warning("STATUS_FILE_INVALID")

    def snapshot(self):
        with self._mutex:
            return replace(self.state)

    def _set(self, **values):
        with self._mutex:
            self.state = replace(self.state, **values)

    def configure_consent(self, consent, automatic):
        self.preferences.save({"consent": consent, "auto_sync": automatic and consent})
        if not consent and self.snapshot().phase == "syncing":
            self.cancel()

    def maybe_auto_start(self):
        with self._mutex:
            if self._automatic_attempted:
                return False
            self._automatic_attempted = True
        settings = self.preferences.load()
        if settings["auto_sync"]:
            return self.start_sync()
        return False

    def _launch(self, target):
        with self._mutex:
            if self.state.phase in {"syncing", "importing"}:
                return False
            try:
                self._writer.acquire(timeout=0)
            except Timeout:
                self.state.message = "Hi ha una altra importació o sincronització activa"
                return False
            self._cancel.clear()
            self.state.phase = "syncing" if target == self._sync else "importing"
            self.state.new = self.state.updated = self.state.pages = self.state.errors = 0
            self.state.outcome = None
            self.thread = threading.Thread(target=self._work, args=(target,), daemon=True)
            try:
                self.thread.start()
            except BaseException:
                self.state.phase = "idle"
                self._writer.release()
                raise
        return True

    def _work(self, target):
        try:
            target()
        except Exception:
            # No str(exc), traceback, cos HTTP, URL de DB ni noms de fitxers als logs.
            self.logger.error("LOCAL_JOB_FAILED")
            self._set(
                message="No s'ha pogut completar. Les dades locals es conserven.",
                errors=1,
                outcome="failed",
            )
        finally:
            self._set(phase="idle", revision=self.snapshot().revision + 1)
            self._writer.release()

    def start_sync(self):
        settings = self.preferences.load()
        if not self.contract_validated:
            self._set(
                message="Connexió bloquejada: contracte API complet pendent de validar",
                connection="Bloquejada pel contracte",
            )
            return False
        if not settings["consent"] or not settings["credential_configured"]:
            self._set(
                message="Cal configurar la clau i autoritzar la primera connexió",
                connection="Sense autorització o credencial",
            )
            return False
        return self._launch(self._sync)

    def _sync(self):
        key = self.credentials.get()
        if not key:
            self._set(connection="Sense credencial", message="No hi ha cap clau al gestor segur")
            return
        repo = Repository(self.paths.database_url, self.paths.root)
        client = self.client_factory(key, approved=True, contract_verified=True)
        key = None
        try:
            self._set(connection="Comprovant Garmin", message="Consultant el catàleg…")

            # La cerca oficial és també la comprovació de connectivitat; no hi ha probes
            # a dominis de tercers ni peticions de salut addicionals.
            first_notification = True

            def progress(value):
                nonlocal first_notification
                connection = "Comprovant Garmin" if first_notification else "Connectat"
                first_notification = False
                self._set(
                    connection=connection,
                    pages=value["pages"],
                    new=value["new"],
                    updated=value["updated"],
                    message="Sincronitzant en segon pla…",
                    run_id=value["run_id"],
                )
                atomic_json(self.paths.root / "sync-status.json", asdict(self.snapshot()))

            resume = self.snapshot().run_id
            if resume and repo.sync_status(resume) not in {
                "failed",
                "interrupted",
                "running",
                "page_limit",
                "verifying",
            }:
                resume = None
            run_id = Synchronizer(client, repo).run(
                resume=resume, page_size=20, progress=progress, cancelled=self._cancel.is_set
            )
            result = repo.sync_status(run_id)
            stamp = datetime.now(UTC).isoformat() if result in {"exhausted", "unstable"} else None
            self._set(
                run_id=run_id,
                last_sync=stamp or self.snapshot().last_sync,
                outcome=result,
                message="Sincronització acabada" if stamp else "Sincronització interrompuda",
            )
            atomic_json(self.paths.root / "sync-status.json", asdict(self.snapshot()))
        except SyncCancelled:
            self._set(
                message="Sincronització interrompuda; es reprendrà des del catàleg",
                outcome="interrupted",
            )
            atomic_json(self.paths.root / "sync-status.json", asdict(self.snapshot()))
        except GarminError:
            self._set(
                connection="Garmin no disponible o autenticació rebutjada",
                message="Treballant amb l'historial local",
                errors=1,
                outcome="failed",
            )
            self.logger.warning("GARMIN_SYNC_UNAVAILABLE")
        finally:
            client.close()
            repo.engine.dispose()

    def start_import(self, path: Path):
        def import_job():
            self._set(message="Important fitxers locals en segon pla…")
            repo = Repository(self.paths.database_url, self.paths.root)
            try:
                report = Importer(repo).import_path(path)
                self._set(
                    message=f"Importació: {report.imported} entrades acceptades; "
                    f"{len(report.errors)} errors",
                    errors=len(report.errors),
                    outcome="imported",
                )
            finally:
                repo.engine.dispose()

        return self._launch(import_job)

    def start_backup(self):
        def backup_job():
            self._set(message="Creant còpia local en segon pla…")
            repo = Repository(self.paths.database_url, self.paths.root)
            try:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                repo.snapshot_directory(self.paths.root / "backups" / stamp)
                self._set(message="Còpia local creada a la carpeta backups", outcome="backed_up")
            finally:
                repo.engine.dispose()

        return self._launch(backup_job)

    def cancel(self):
        self._cancel.set()
        self._set(message="S'aturarà al proper punt segur; no es perdran pàgines compromeses")
