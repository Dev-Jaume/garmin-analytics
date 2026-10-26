"""Importa FIT i ZIP (incloent ZIP imbricats) sense extreure rutes de l'arxiu."""

import io
import json
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from sqlalchemy import insert, select

from garmin_running.domain import ActivityData, DataError, instant
from garmin_running.fit.parser import MAX_FIT_BYTES, parse_fit
from garmin_running.storage.repository import Repository, aliases, import_runs


@dataclass
class ImportReport:
    imported: int = 0  # Fitxers acceptats; pot incloure reimports idempotents.
    ignored: int = 0
    errors: list[dict] = field(default_factory=list)


def summary_data(item: dict) -> ActivityData:
    """Adaptador conservador Garmin summarizedActivitiesExport; manté l'original."""
    start = instant(item.get("startTimeGMT"))
    sport = item.get("activityType", {})
    sport = sport.get("typeKey", "unknown") if isinstance(sport, dict) else str(sport)
    return ActivityData(
        start=start,
        sport=sport,
        metrics={},  # Les unitats dels resums no es poden assumir sense validar-ne el format.
        flags=["summary_only", "export_units_require_confirmation"],
        messages=[{"name": "garmin_summary", "original": item}],
    )


class Importer:
    def __init__(
        self,
        repo: Repository,
        max_total_bytes: int = 512 * 1024 * 1024,
        max_members: int = 10000,
        max_depth: int = 4,
    ):
        self.repo = repo
        self.max_total_bytes = max_total_bytes
        self.max_members = max_members
        self.max_depth = max_depth
        self.used = 0
        self.members = 0

    def import_path(self, path: Path, activity_id: str | None = None) -> ImportReport:
        if activity_id is not None and (not path.is_file() or path.suffix.lower() != ".fit"):
            raise ValueError("activityId explícit només per a un FIT individual")
        self.activity_id = activity_id
        self.used = self.members = 0
        report = ImportReport()
        paths = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        for file in paths:
            if path.is_dir():
                # El límit protegeix cada contenidor, no tot un historial de milers de FIT.
                self.used = self.members = 0
            if file.is_symlink():
                report.ignored += 1
                continue
            try:
                if file.stat().st_size > self.max_total_bytes:
                    raise DataError("Fitxer superior al límit configurat")
                self._consume(file.name, file.read_bytes(), report, 0)
            except (OSError, ValueError, zipfile.BadZipFile):
                report.errors.append({"entry": file.name, "error": "Importació rebutjada"})
        with self.repo.engine.begin() as conn:
            conn.execute(
                insert(import_runs).values(
                    id=str(uuid4()), at=datetime.now(UTC).isoformat(), report=asdict(report)
                )
            )
        return report

    def _consume(self, name: str, data: bytes, report: ImportReport, depth: int) -> None:
        self.used += len(data)
        self.members += 1
        if self.used > self.max_total_bytes or self.members > self.max_members:
            raise DataError("Límit acumulat d'importació superat")
        suffix = PurePosixPath(name).suffix.lower()
        if suffix == ".zip" or data[:4] == b"PK\x03\x04":
            if depth >= self.max_depth:
                raise DataError("Massa nivells ZIP")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for entry in archive.infolist():
                    if entry.is_dir():
                        continue
                    try:
                        if (
                            self.members >= self.max_members
                            or entry.file_size > MAX_FIT_BYTES
                            or entry.flag_bits & 1
                            or entry.file_size > self.max_total_bytes - self.used
                        ):
                            raise DataError("Entrada ZIP excessiva o xifrada")
                        self._consume(entry.filename, archive.read(entry), report, depth + 1)
                    except (ValueError, RuntimeError, zipfile.BadZipFile):
                        report.errors.append(
                            {"entry": entry.filename, "error": "Entrada rebutjada"}
                        )
        elif suffix == ".fit":
            # Arxiva fins i tot el FIT rebutjat per poder auditar-lo.
            self.repo.archive(data)
            parsed = parse_fit(data)
            with self.repo.engine.begin() as conn:
                self.repo.save(conn, parsed, data, "fit_export", self.activity_id)
            report.imported += 1
        elif suffix == ".json":
            obj = json.loads(data)
            # No interpretar formats arbitraris com si fossin resums Garmin.
            if not isinstance(obj, list) or not all(
                isinstance(i, dict) and isinstance(i.get("summarizedActivitiesExport"), list)
                for i in obj
            ):
                report.ignored += 1
                return
            self.repo.archive(data)
            for group in obj:
                for item in group["summarizedActivitiesExport"]:
                    try:
                        if not isinstance(item, dict) or "activityId" not in item:
                            raise DataError("Resum sense identificador")
                        parsed = summary_data(item)
                        # Els resums no poden degradar un FIT ja disponible.
                        parsed.identity = None
                        with self.repo.engine.begin() as conn:
                            known = conn.execute(
                                select(aliases.c.activity_id).where(
                                    aliases.c.alias == f"garmin:{item['activityId']}"
                                )
                            ).first()
                            if not known:
                                self.repo.save(
                                    conn,
                                    parsed,
                                    json.dumps(item, sort_keys=True).encode(),
                                    "garmin_summary_export",
                                    str(item["activityId"]),
                                )
                        report.imported += 1
                    except (ValueError, TypeError):
                        report.errors.append({"entry": name, "error": "Resum rebutjat"})
        else:
            report.ignored += 1
