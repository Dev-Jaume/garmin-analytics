"""SQLAlchemy portable + fitxers originals direccionats pel seu SHA-256."""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    func,
    insert,
    inspect,
    select,
    update,
)
from sqlalchemy.engine import Connection

from garmin_running.domain import ALGORITHM_VERSION, ActivityData

metadata = MetaData()
activities = Table(
    "activities",
    metadata,
    Column("id", String, primary_key=True),
    Column("start", String, index=True),
    Column("sport", String),
    Column("current", JSON, nullable=False),
)
aliases = Table(
    "aliases",
    metadata,
    Column("alias", String, primary_key=True),
    Column("activity_id", String, ForeignKey("activities.id"), nullable=False),
)
versions = Table(
    "versions",
    metadata,
    Column("id", String, primary_key=True),
    Column("activity_id", String, ForeignKey("activities.id"), nullable=False),
    Column("digest", String, nullable=False),
    Column("source", String, nullable=False),
    Column("imported_at", String, nullable=False),
    Column("algorithm", String, nullable=False),
    Column("original_path", String, nullable=False),
    Column("payload", JSON, nullable=False),
)
sync_runs = Table(
    "sync_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("status", String),
    Column("next_offset", Integer, nullable=False),
    Column("pages", Integer, nullable=False),
    Column("audit", JSON, nullable=False),
)
import_runs = Table(
    "import_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("at", String, nullable=False),
    Column("report", JSON, nullable=False),
)
SCHEMA_VERSION = "1"
schema = Table("schema_version", metadata, Column("version", String, primary_key=True))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


class Repository:
    def __init__(self, url: str, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine = create_engine(url)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def sqlite_options(dbapi_connection, _record):
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
                dbapi_connection.execute("PRAGMA busy_timeout=5000")

        # Comprovar abans de crear taules: no mutar una DB estranya/incompatible.
        try:
            existing_tables = set(inspect(self.engine).get_table_names())
            if existing_tables:
                if "schema_version" not in existing_tables:
                    raise ValueError("DB existent sense versió; cal migració explícita")
                with self.engine.connect() as conn:
                    existing_version = conn.execute(select(schema.c.version)).scalars().all()
                if existing_version != [SCHEMA_VERSION]:
                    raise ValueError("Versió de DB incompatible; cal migració")
        except Exception:
            self.engine.dispose()
            raise
        metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite" and self.engine.url.database not in (
            None,
            ":memory:",
        ):
            Path(self.engine.url.database).chmod(0o600)
        with self.engine.begin() as conn:
            existing = conn.execute(select(schema.c.version)).scalars().all()
            if existing and existing != [SCHEMA_VERSION]:
                raise ValueError("Versió de DB incompatible; cal migració")
            if not existing:
                conn.execute(insert(schema).values(version=SCHEMA_VERSION))

    def archive(self, raw: bytes) -> tuple[str, str]:
        sha = digest(raw)
        relative = Path("originals") / sha[:2] / sha
        target = self.data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists():
            if digest(target.read_bytes()) != sha:
                raise ValueError("Original arxivat amb integritat incorrecta")
        else:
            fd, name = tempfile.mkstemp(dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        return sha, str(relative)

    def save(
        self,
        conn: Connection,
        data: ActivityData,
        raw: bytes,
        source: str,
        activity_id: str | None = None,
    ) -> str:
        sha, path = self.archive(raw)
        keys = [f"sha256:{sha}"]
        if data.identity:
            keys.append(data.identity)
        if activity_id is not None:
            if not str(activity_id).isdigit():
                raise ValueError("activityId invàlid")
            keys.insert(0, f"garmin:{activity_id}")
        matches = set(
            conn.execute(select(aliases.c.activity_id).where(aliases.c.alias.in_(keys))).scalars()
        )
        if len(matches) > 1:
            raise ValueError("Conflicte d'identitat: cal revisió; no fusionat automàticament")
        entity_id = next(iter(matches), str(uuid4()))
        payload = asdict(data)
        if data.start:
            candidates = (
                conn.execute(
                    select(activities.c.id).where(
                        activities.c.start == data.start,
                        activities.c.sport == data.sport,
                        activities.c.id != entity_id,
                    )
                )
                .scalars()
                .all()
            )
            if candidates:
                payload["flags"] = payload["flags"] + ["possible_duplicate_requires_review"]
        version_digest = digest(canonical({"original_sha256": sha, "payload": payload}))
        exists = conn.execute(
            select(activities.c.current).where(activities.c.id == entity_id)
        ).first()
        known_original = conn.execute(
            select(aliases.c.alias).where(aliases.c.alias == f"sha256:{sha}")
        ).first()
        preserve_enrichment = bool(
            source == "fit_export"
            and known_original
            and exists
            and any(m.get("name") == "api_detail" for m in exists[0]["messages"])
        )
        if not exists:
            conn.execute(
                insert(activities).values(
                    id=entity_id, start=data.start, sport=data.sport, current=payload
                )
            )
        # Reimportar una versió antiga no reverteix la versió actual.
        same = conn.execute(
            select(versions.c.id).where(
                versions.c.activity_id == entity_id, versions.c.digest == version_digest
            )
        ).first()
        if not same:
            conn.execute(
                insert(versions).values(
                    id=str(uuid4()),
                    activity_id=entity_id,
                    digest=version_digest,
                    source=source,
                    imported_at=datetime.now(UTC).isoformat(),
                    algorithm=ALGORITHM_VERSION,
                    original_path=path,
                    payload=payload,
                )
            )
            if not preserve_enrichment:
                conn.execute(
                    update(activities)
                    .where(activities.c.id == entity_id)
                    .values(start=data.start, sport=data.sport, current=payload)
                )
        for key in keys:
            if conn.execute(select(aliases.c.alias).where(aliases.c.alias == key)).first() is None:
                conn.execute(insert(aliases).values(alias=key, activity_id=entity_id))
        return entity_id

    def list_activities(self) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(select(activities)).mappings()]

    def coverage(self, gap_days: int = 30) -> dict:
        with self.engine.connect() as conn:
            count, oldest, newest = conn.execute(
                select(func.count(), func.min(activities.c.start), func.max(activities.c.start))
            ).one()
            runs = [dict(r) for r in conn.execute(select(sync_runs)).mappings()]
            imports = [dict(r) for r in conn.execute(select(import_runs)).mappings()]
            dates = (
                conn.execute(
                    select(activities.c.start)
                    .where(activities.c.start.is_not(None))
                    .order_by(activities.c.start)
                )
                .scalars()
                .all()
            )
            payloads = conn.execute(select(activities.c.current)).scalars().all()
        gaps = [
            {
                "from": a,
                "to": b,
                "days": (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
                / 86400,
            }
            for a, b in zip(dates, dates[1:], strict=False)
            if (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days >= gap_days
        ]
        return {
            "status": "Cobertura no verificada",
            "activities": count,
            "oldest": oldest,
            "newest": newest,
            "sync_runs": runs,
            "imports": imports,
            "possible_gaps": gaps,
            "gap_days_policy": gap_days,
            "without_start": sum(p["start"] is None for p in payloads),
            "without_records": sum(not p["samples"] for p in payloads),
            "possible_duplicates": sum(
                "possible_duplicate_requires_review" in p["flags"] for p in payloads
            ),
            "limitations": [
                "Sense inventari extern no es pot demostrar exhaustivitat",
                "Els intervals sense activitats no demostren pèrdua de dades",
            ],
        }
