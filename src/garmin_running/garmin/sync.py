"""Pàgines transaccionals i represa conservadora; mai afirma cobertura completa."""

import io
import zipfile
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select, update

from garmin_running.domain import DataError
from garmin_running.fit.parser import MAX_FIT_BYTES, parse_fit
from garmin_running.garmin.client import GarminClient, GarminError
from garmin_running.storage.repository import Repository, aliases, canonical, digest, sync_runs


def downloaded_fit(data: bytes) -> bytes:
    if data[:4] != b"PK\x03\x04":
        if len(data) > MAX_FIT_BYTES:
            raise DataError("Descàrrega massa gran")
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = [e for e in archive.infolist() if e.filename.lower().endswith(".fit")]
        if len(files) != 1 or files[0].file_size > MAX_FIT_BYTES or files[0].flag_bits & 1:
            raise DataError("Descàrrega ZIP amb FIT ambigu o excessiu")
        return archive.read(files[0])


class Synchronizer:
    def __init__(self, client: GarminClient, repo: Repository):
        self.client, self.repo = client, repo

    def run(
        self,
        *,
        resume: str | None = None,
        page_size: int = 50,
        max_pages: int = 10000,
        refresh: bool = False,
    ) -> str:
        if not 1 <= page_size <= 100 or max_pages < 1:
            raise ValueError("Límits de sincronització invàlids")
        run_id = resume or str(uuid4())
        with self.repo.engine.begin() as conn:
            if resume:
                row = (
                    conn.execute(select(sync_runs).where(sync_runs.c.id == resume)).mappings().one()
                )
                audit = dict(row["audit"])
                if audit["page_size"] != page_size:
                    raise ValueError("Cal reprendre amb la mateixa mida de pàgina")
                # Repassar una pàgina redueix el risc d'offset desplaçat; no és una snapshot.
                offset, pages = max(0, row["next_offset"] - page_size), row["pages"]
            else:
                offset, pages = 0, 0
                audit = {
                    "page_size": page_size,
                    "status": "Cobertura no verificada",
                    "started_at": datetime.now(UTC).isoformat(),
                    "page_log": [],
                    "summary_hashes": {},
                    "warnings": [
                        "Paginació mutable: altes o baixes poden desplaçar offsets",
                        "La reconciliació completa periòdica continua sent necessària",
                    ],
                }
                conn.execute(
                    insert(sync_runs).values(
                        id=run_id, status="running", next_offset=0, pages=0, audit=audit
                    )
                )
        # Carregar signatures una vegada; evita rellegir tot l'historial per activitat.
        with self.repo.engine.connect() as conn:
            past_runs = (
                conn.execute(
                    select(sync_runs.c.audit).where(
                        sync_runs.c.status == "exhausted", sync_runs.c.id != run_id
                    )
                )
                .scalars()
                .all()
            )
        previous_hashes = {}
        for past_audit in sorted(past_runs, key=lambda a: a["started_at"]):
            previous_hashes.update(past_audit.get("summary_hashes", {}))
        fingerprints: set[str] = set()
        try:
            for _ in range(max_pages):
                items = self.client.search(offset, page_size)
                page_hash = digest(canonical(items))
                if items and page_hash in fingerprints:
                    raise GarminError("Pàgina repetida; s'atura per evitar bucle")
                fingerprints.add(page_hash)
                with self.repo.engine.begin() as conn:
                    for item in items:
                        activity_id = str(item.get("activityId", ""))
                        if not activity_id.isdigit():
                            raise GarminError("Pàgina amb activityId no vàlid")
                        summary_hash = digest(canonical(item))
                        known = conn.execute(
                            select(aliases.c.activity_id).where(
                                aliases.c.alias == f"garmin:{activity_id}"
                            )
                        ).first()
                        # Les signatures només són d'aquesta execució o de l'anterior completada.
                        previous_hash = audit["summary_hashes"].get(activity_id)
                        if previous_hash is None:
                            previous_hash = previous_hashes.get(activity_id)
                        if refresh or not known or previous_hash != summary_hash:
                            detail = self.client.detail(activity_id)
                            raw_download = self.client.download(activity_id)
                            self.repo.archive(raw_download)
                            raw = downloaded_fit(raw_download)
                            parsed = parse_fit(raw)
                            parsed.messages.append({"name": "api_detail", "original": detail})
                            parsed.messages.append({"name": "api_summary", "original": item})
                            # Conserva també versions dels detalls JSON sense mutar el FIT.
                            self.repo.archive(canonical(detail))
                            self.repo.save(conn, parsed, raw, "personal_api", activity_id)
                        audit["summary_hashes"][activity_id] = summary_hash
                    pages += 1
                    audit["page_log"].append(
                        {"offset": offset, "count": len(items), "at": datetime.now(UTC).isoformat()}
                    )
                    offset += len(items)
                    status = "exhausted" if not items else "running"
                    conn.execute(
                        update(sync_runs)
                        .where(sync_runs.c.id == run_id)
                        .values(status=status, next_offset=offset, pages=pages, audit=audit)
                    )
                if not items:
                    return run_id
            with self.repo.engine.begin() as conn:
                conn.execute(
                    update(sync_runs).where(sync_runs.c.id == run_id).values(status="page_limit")
                )
            return run_id
        except Exception:
            # La pàgina fallida es reprocessarà. No guardar el cos ni missatge de l'excepció.
            with self.repo.engine.begin() as conn:
                conn.execute(
                    update(sync_runs).where(sync_runs.c.id == run_id).values(status="failed")
                )
            raise
