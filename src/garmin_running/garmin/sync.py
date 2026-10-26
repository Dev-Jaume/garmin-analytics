"""HTTP i staging durables fora de SQL; commit atòmic d'activitats i checkpoint."""

import io
import json
import os
import tempfile
import zipfile
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update

from garmin_running.domain import ActivityData, DataError
from garmin_running.fit.parser import MAX_FIT_BYTES, parse_fit
from garmin_running.garmin.client import GarminClient, GarminError
from garmin_running.storage.repository import Repository, aliases, canonical, digest, sync_runs


def downloaded_fit(data: bytes) -> bytes:
    """ZIP és el format oficial; FIT directe només és una compatibilitat local."""
    if data[:4] != b"PK\x03\x04":
        if len(data) > MAX_FIT_BYTES:
            raise DataError("Descàrrega massa gran")
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = [e for e in archive.infolist() if e.filename.lower().endswith(".fit")]
        if len(files) != 1 or files[0].file_size > MAX_FIT_BYTES or files[0].flag_bits & 1:
            raise DataError("Descàrrega ZIP amb FIT ambigu o excessiu")
        return archive.read(files[0])


def now() -> str:
    return datetime.now(UTC).isoformat()


def ids_of(items: list[dict]) -> list[str]:
    return [GarminClient._id(item.get("activityId", "")) for item in items]


class Synchronizer:
    def __init__(self, client: GarminClient, repo: Repository):
        self.client, self.repo = client, repo

    def _original(self, sha: str) -> tuple[bytes, str]:
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise DataError("Referència de staging invàlida")
        relative = str(Path("originals") / sha[:2] / sha)
        try:
            raw = (self.repo.data_dir / relative).read_bytes()
        except OSError:
            raise DataError("Original de staging absent") from None
        if digest(raw) != sha:
            raise DataError("Integritat de staging incorrecta")
        return raw, relative

    def _stage_path(self, run_id: str, activity_id: str, summary_hash: str) -> Path:
        return self.repo.data_dir / "staging" / run_id / f"{activity_id}-{summary_hash}.json"

    @staticmethod
    def _write_stage(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            if os.name == "posix":
                directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _prepare(self, run_id: str, item: dict) -> tuple[ActivityData, str, str]:
        """Reutilitza staging íntegre de la mateixa execució, també després d'un crash."""
        activity_id = GarminClient._id(item["activityId"])
        summary_hash = digest(canonical(item))
        path = self._stage_path(run_id, activity_id, summary_hash)
        if not path.exists():
            detail = self.client.detail(activity_id)
            if "activityId" in detail and str(detail["activityId"]) != activity_id:
                raise DataError("El detall no correspon a l'activitat sol·licitada")
            download = self.client.download(activity_id)
            download_sha, _ = self.repo.archive(download)
            raw = downloaded_fit(download)
            fit_sha, _ = self.repo.archive(raw)
            parsed = parse_fit(raw)
            parsed.messages.extend(
                [
                    {"name": "api_detail", "original": detail},
                    {"name": "api_summary", "original": item},
                ]
            )
            detail_sha, _ = self.repo.archive(canonical(detail))
            payload_sha, _ = self.repo.archive(canonical(asdict(parsed)))
            summary_sha, _ = self.repo.archive(canonical(item))
            body = {
                "activity_id": activity_id,
                "summary_hash": summary_hash,
                "refs": {
                    "fit": fit_sha,
                    "download": download_sha,
                    "detail": detail_sha,
                    "payload": payload_sha,
                    "summary": summary_sha,
                },
            }
            self._write_stage(path, {"body": body, "sha256": digest(canonical(body))})
        try:
            envelope = json.loads(path.read_bytes())
            body = envelope["body"]
            if (
                digest(canonical(body)) != envelope["sha256"]
                or body["activity_id"] != activity_id
                or body["summary_hash"] != summary_hash
            ):
                raise DataError("Manifest de staging inconsistent")
            refs = body["refs"]
            originals = {
                key: self._original(refs[key])
                for key in ("fit", "download", "detail", "payload", "summary")
            }
            if originals["summary"][0] != canonical(item):
                raise DataError("Resum de staging inconsistent")
            if downloaded_fit(originals["download"][0]) != originals["fit"][0]:
                raise DataError("FIT i contenidor de staging inconsistents")
            data = ActivityData(**json.loads(originals["payload"][0]))
            return data, refs["fit"], originals["fit"][1]
        except (KeyError, TypeError, ValueError, OSError):
            raise DataError("Staging invàlid; conservar i revisar abans de reprendre") from None

    def _start(self, resume: str | None, page_size: int) -> tuple[str, dict, int]:
        run_id = str(UUID(resume)) if resume else str(uuid4())
        with self.repo.engine.begin() as conn:
            known_ids = [
                key.removeprefix("garmin:")
                for key in conn.execute(
                    select(aliases.c.alias).where(aliases.c.alias.like("garmin:%"))
                ).scalars()
            ]
            if resume:
                row = (
                    conn.execute(select(sync_runs).where(sync_runs.c.id == run_id)).mappings().one()
                )
                audit = deepcopy(row["audit"])
                if audit["page_size"] != page_size:
                    raise ValueError("Cal reprendre amb la mateixa mida de pàgina")
                audit.setdefault("resume_log", []).append(
                    {
                        "at": now(),
                        "previous_next_offset": row["next_offset"],
                        "pending_page": deepcopy(audit.get("pending_page")),
                        "strategy": "restart_from_zero",
                    }
                )
                if audit.get("reconciliation") is not None:
                    audit.setdefault("reconciliation_history", []).append(
                        {
                            "attempt": audit.get("attempt", 0),
                            "result": deepcopy(audit["reconciliation"]),
                        }
                    )
                pages = row["pages"]
            else:
                pages = 0
                audit = {
                    "page_size": page_size,
                    "status": "Cobertura no verificada",
                    "started_at": now(),
                    "page_log": [],
                    "summary_hashes": {},
                    "issues": [],
                    "failure_log": [],
                    "attempt": -1,
                    "warnings": [
                        "Cap passada prova exhaustivitat sense inventari extern",
                        "Els IDs Garmin no són una seqüència numèrica contigua",
                    ],
                }
            audit.update(
                audit_version=2,
                attempt=audit.get("attempt", -1) + 1,
                scan_ids=[],
                scan_sequence=[],
                scan_hashes={},
                baseline_ids=known_ids,
                reconciliation=None,
            )
            audit.setdefault("issues", [])
            audit.setdefault("failure_log", [])
            values = dict(status="running", next_offset=0, pages=pages, audit=audit)
            if resume:
                conn.execute(update(sync_runs).where(sync_runs.c.id == run_id).values(**values))
            else:
                conn.execute(insert(sync_runs).values(id=run_id, **values))
        return run_id, audit, pages

    def _reconcile(self, audit: dict, page_size: int, max_pages: int) -> dict:
        """Segona lectura del catàleg, sense descàrregues ni transaccions SQL."""
        sequence, hashes, page_log, issues = [], {}, [], []
        offset = 0
        fingerprints = set()
        complete = False
        audit["reconciliation"] = {"status": "in_progress", "pages": page_log}
        for _ in range(max_pages):
            items = self.client.search(offset, page_size)
            ids = ids_of(items)
            fingerprint = digest(canonical(items))
            page_log.append({"offset": offset, "ids": ids, "hash": fingerprint, "at": now()})
            if items and fingerprint in fingerprints:
                issues.append("repeated_page")
                break
            fingerprints.add(fingerprint)
            sequence.extend(ids)
            for item, activity_id in zip(items, ids, strict=True):
                if activity_id in hashes:
                    issues.append("duplicate_id")
                hashes[activity_id] = digest(canonical(item))
            offset += len(items)
            if not items:
                complete = True
                break
        primary = set(audit["scan_ids"])
        current = set(sequence)
        result = {
            "complete": complete,
            "pages": page_log,
            "issues": sorted(set(issues)),
            "new_ids": sorted(current - primary),
            "missing_ids": sorted(primary - current),
            "changed_summary_ids": sorted(
                k for k in primary & current if hashes[k] != audit["scan_hashes"][k]
            ),
            "sequence_changed": sequence != audit["scan_sequence"],
            "not_seen_since_previous_inventory": sorted(set(audit["baseline_ids"]) - current),
        }
        result["status"] = (
            "stable"
            if (
                complete
                and not issues
                and not result["new_ids"]
                and not result["missing_ids"]
                and not result["changed_summary_ids"]
                and not result["sequence_changed"]
                and not result["not_seen_since_previous_inventory"]
            )
            else "changed_or_incomplete"
        )
        return result

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
        run_id, audit, pages = self._start(resume, page_size)
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
            known = set(conn.execute(select(aliases.c.alias)).scalars())
        previous_hashes = {}
        for past in sorted(past_runs, key=lambda a: a["started_at"]):
            previous_hashes.update(past.get("summary_hashes", {}))
        previous_hashes.update(audit["summary_hashes"])
        fingerprints = set()
        offset, phase = 0, "search"
        try:
            for _ in range(max_pages):
                phase = "search"
                items = self.client.search(offset, page_size)
                ids = ids_of(items)
                fingerprint = digest(canonical(items))
                issue = {
                    "attempt": audit["attempt"],
                    "offset": offset,
                    "within_page_duplicates": sorted(k for k, n in Counter(ids).items() if n > 1),
                    "cross_page_duplicates": sorted(set(ids) & set(audit["scan_ids"])),
                }
                if issue["within_page_duplicates"] or issue["cross_page_duplicates"]:
                    audit["issues"].append(issue)
                if items and fingerprint in fingerprints:
                    audit["issues"].append(
                        {"code": "repeated_page", "offset": offset, "attempt": audit["attempt"]}
                    )
                    raise GarminError("Pàgina repetida; s'atura per evitar bucle")
                fingerprints.add(fingerprint)
                unique = {}
                for item, activity_id in zip(items, ids, strict=True):
                    if activity_id in unique and unique[activity_id] != item:
                        audit["issues"].append(
                            {
                                "code": "conflicting_duplicate",
                                "id": activity_id,
                                "attempt": audit["attempt"],
                            }
                        )
                        raise GarminError("ID duplicat amb contingut incompatible")
                    unique[activity_id] = item
                audit["pending_page"] = {"offset": offset, "ids": ids, "hash": fingerprint}
                phase = "prepare"
                prepared = []
                for activity_id, item in unique.items():
                    summary_hash = digest(canonical(item))
                    if (
                        activity_id in audit["scan_hashes"]
                        and audit["scan_hashes"][activity_id] != summary_hash
                    ):
                        audit["issues"].append(
                            {
                                "code": "changed_during_scan",
                                "id": activity_id,
                                "attempt": audit["attempt"],
                            }
                        )
                    if (
                        refresh
                        or f"garmin:{activity_id}" not in known
                        or previous_hashes.get(activity_id) != summary_hash
                    ):
                        prepared.append((activity_id, self._prepare(run_id, item)))
                # Només ara, amb totes les peticions tancades i FIT durables, obrir SQL.
                next_audit = deepcopy(audit)
                next_audit["pending_page"] = None
                for activity_id, item in unique.items():
                    next_audit["summary_hashes"][activity_id] = digest(canonical(item))
                    next_audit["scan_hashes"][activity_id] = digest(canonical(item))
                next_audit["scan_ids"] = sorted(set(audit["scan_ids"]) | set(ids))
                next_audit["scan_sequence"].extend(ids)
                next_audit["page_log"].append(
                    {
                        "attempt": audit["attempt"],
                        "offset": offset,
                        "count": len(items),
                        "ids": ids,
                        "hash": fingerprint,
                        "at": now(),
                    }
                )
                next_offset = offset + len(items)
                phase = "persist"
                with self.repo.engine.begin() as conn:
                    for activity_id, (data, sha, path) in prepared:
                        self.repo.save_archived(conn, data, sha, path, "personal_api", activity_id)
                    result = conn.execute(
                        update(sync_runs)
                        .where(
                            sync_runs.c.id == run_id,
                            sync_runs.c.pages == pages,
                            sync_runs.c.status == "running",
                        )
                        .values(
                            status="running" if items else "verifying",
                            next_offset=next_offset,
                            pages=pages + 1,
                            audit=next_audit,
                        )
                    )
                    if result.rowcount != 1:
                        raise GarminError("Checkpoint modificat per una altra execució")
                audit, pages, offset = next_audit, pages + 1, next_offset
                known.update(f"garmin:{key}" for key in unique)
                previous_hashes.update(audit["summary_hashes"])
                if not items:
                    phase = "reconcile"
                    audit["reconciliation"] = self._reconcile(audit, page_size, max_pages)
                    current_issues = [
                        i
                        for i in audit["issues"]
                        if i.get("attempt", audit["attempt"]) == audit["attempt"]
                    ]
                    status = (
                        "exhausted"
                        if audit["reconciliation"]["status"] == "stable" and not current_issues
                        else "unstable"
                    )
                    with self.repo.engine.begin() as conn:
                        conn.execute(
                            update(sync_runs)
                            .where(sync_runs.c.id == run_id)
                            .values(status=status, audit=audit)
                        )
                    return run_id
            with self.repo.engine.begin() as conn:
                conn.execute(
                    update(sync_runs).where(sync_runs.c.id == run_id).values(status="page_limit")
                )
            return run_id
        except BaseException as exc:
            # També registra KeyboardInterrupt; SIGKILL deixa staging reutilitzable.
            audit["failure_log"].append(
                {"at": now(), "offset": offset, "phase": phase, "type": type(exc).__name__}
            )
            with self.repo.engine.begin() as conn:
                conn.execute(
                    update(sync_runs)
                    .where(sync_runs.c.id == run_id, sync_runs.c.pages == pages)
                    .values(
                        status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                        audit=audit,
                    )
                )
            raise
