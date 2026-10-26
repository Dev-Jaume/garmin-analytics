import io
import json
import zipfile
from datetime import UTC, datetime

import pytest
from conftest import synthetic_fit
from sqlalchemy import func, select

from garmin_running.domain import DataError, instant
from garmin_running.fit.parser import parse_fit
from garmin_running.ingestion.importer import Importer, summary_data
from garmin_running.storage.repository import versions


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return stream.getvalue()


def test_binary_fit_roundtrip(fit_bytes):
    parsed = parse_fit(fit_bytes)
    assert parsed.sport == "running"
    assert parsed.is_running
    assert parsed.metrics["distance_m"] == 5000
    assert parsed.metrics["elapsed_s"] == 1500
    assert parsed.metrics["timer_s"] == 1400
    assert parsed.metrics["moving_s"] is None
    assert parsed.metrics["avg_pace_seconds_per_km"] == 280
    assert parsed.timezone is None
    assert len(parsed.events) == 1
    assert parsed.events[0]["event_type"] == "stop_all"
    assert parsed.samples[0]["speed_mps"] == 3
    assert parsed.samples[-1]["heart_rate"] is None
    assert parsed.samples[-1]["pace_seconds_per_km"] is None
    assert parsed.samples[0]["altitude_m"] is None
    record = next(m for m in parsed.messages if m["name"] == "record")
    speed = next(f for f in record["fields"] if f["name"] == "speed")
    assert speed["units"] == "m/s"
    assert speed["raw_value"] == 3000


def test_irregular_and_duplicate_samples_preserved():
    parsed = parse_fit(synthetic_fit(duplicate=True))
    assert len(parsed.samples) == 4
    assert "duplicate_timestamp" in parsed.samples[-1]["quality_flags"]
    times = [datetime.fromisoformat(r["timestamp"]) for r in parsed.samples]
    assert (times[2] - times[1]).total_seconds() == 10


@pytest.mark.parametrize("data", [b"", b"not fit", synthetic_fit()[:-1]])
def test_invalid_fit(data):
    with pytest.raises(DataError):
        parse_fit(data)


def test_crc_corruption_rejected(fit_bytes):
    bad = bytearray(fit_bytes)
    bad[-1] ^= 1
    with pytest.raises(DataError):
        parse_fit(bytes(bad))


def test_multisport_not_silently_merged():
    with pytest.raises(DataError, match="sessió"):
        parse_fit(synthetic_fit(sessions=2))


def test_idempotency_and_versions(repo, fit_bytes):
    first = parse_fit(fit_bytes)
    with repo.engine.begin() as conn:
        entity = repo.save(conn, first, fit_bytes, "fit_export")
        assert repo.save(conn, first, fit_bytes, "fit_export") == entity
    modified = synthetic_fit(distance=600000)
    with repo.engine.begin() as conn:
        assert repo.save(conn, parse_fit(modified), modified, "fit_export", "123") == entity
        assert repo.save(conn, first, fit_bytes, "fit_export") == entity
        assert conn.execute(select(func.count()).select_from(versions)).scalar_one() == 2
    rows = repo.list_activities()
    assert len(rows) == 1
    assert rows[0]["current"]["metrics"]["distance_m"] == 6000
    assert len(list((repo.data_dir / "originals").rglob("*"))) >= 2


def test_transaction_rollback(repo, fit_bytes):
    with pytest.raises(RuntimeError), repo.engine.begin() as conn:
        repo.save(conn, parse_fit(fit_bytes), fit_bytes, "test")
        raise RuntimeError("simulated crash")
    assert repo.list_activities() == []


def test_nested_export_and_path_traversal_no_extraction(repo, fit_bytes, tmp_path):
    path = tmp_path / "account.zip"
    path.write_bytes(
        zipped(
            {
                "DI_CONNECT/nested.zip": zipped({"../../escape.fit": fit_bytes}),
                "irrelevant.txt": b"unknown",
                "broken.fit": b"bad",
            }
        )
    )
    report = Importer(repo).import_path(path)
    assert report.imported == 1
    assert report.ignored == 1
    assert len(report.errors) == 1
    assert not (tmp_path.parent / "escape.fit").exists()
    assert len(repo.list_activities()) == 1


def test_import_repeat_does_not_duplicate(repo, fit_bytes, tmp_path):
    path = tmp_path / "test.FIT"
    path.write_bytes(fit_bytes)
    importer = Importer(repo)
    assert importer.import_path(path).imported == 1
    assert importer.import_path(path).imported == 1
    assert len(repo.list_activities()) == 1


def test_archive_limits(repo, fit_bytes, tmp_path):
    path = tmp_path / "large.zip"
    path.write_bytes(zipped({"a.fit": fit_bytes, "b.fit": fit_bytes}))
    assert Importer(repo, max_members=1).import_path(path).errors
    assert Importer(repo, max_depth=0).import_path(path).errors
    assert Importer(repo, max_total_bytes=20).import_path(path).errors


def test_import_directory_and_missing_file(repo, fit_bytes, tmp_path):
    path = tmp_path / "exports"
    path.mkdir()
    (path / "one.fit").write_bytes(fit_bytes)
    (path / "other.json").write_text('{"unknown": true}')
    report = Importer(repo).import_path(path)
    assert report.imported == report.ignored == 1
    assert Importer(repo).import_path(tmp_path / "missing.fit").errors


def test_summary_export_is_conservative(repo, tmp_path):
    path = tmp_path / "export.json"
    path.write_text(
        json.dumps(
            [
                {
                    "summarizedActivitiesExport": [
                        {
                            "activityId": 42,
                            "startTimeGMT": "2025-01-01T12:00:00",
                            "activityType": {"typeKey": "running"},
                            "distance": 5000,
                        }
                    ]
                }
            ]
        )
    )
    assert Importer(repo).import_path(path).imported == 1
    assert Importer(repo).import_path(path).imported == 1
    row = repo.list_activities()[0]["current"]
    assert "summary_only" in row["flags"]
    assert row["samples"] == []


def test_timezone_and_incomplete_summary():
    assert instant("2025-01-01T14:00:00+02:00") == "2025-01-01T12:00:00+00:00"
    assert instant(datetime(2025, 1, 1, tzinfo=UTC)).endswith("+00:00")
    assert summary_data({}).start is None
    assert summary_data({}).sport == "unknown"


def test_coverage_always_unverified(repo):
    coverage = repo.coverage()
    assert coverage["activities"] == 0
    assert coverage["oldest"] is coverage["newest"] is None
    assert coverage["status"] == "Cobertura no verificada"


def test_metadata_version_is_saved_with_identical_fit(repo, fit_bytes):
    first = parse_fit(fit_bytes)
    with repo.engine.begin() as conn:
        entity = repo.save(conn, first, fit_bytes, "fit_export")
    enriched = parse_fit(fit_bytes)
    enriched.messages.append({"name": "api_detail", "original": {"label": "synthetic"}})
    with repo.engine.begin() as conn:
        assert repo.save(conn, enriched, fit_bytes, "personal_api", "1") == entity
        assert conn.execute(select(func.count()).select_from(versions)).scalar_one() == 2
    assert repo.list_activities()[0]["current"]["messages"][-1]["name"] == "api_detail"


def test_possible_duplicates_are_flagged_conservatively(repo):
    for serial in [1, 2]:
        data = synthetic_fit(serial=serial)
        with repo.engine.begin() as conn:
            repo.save(conn, parse_fit(data), data, "fit_export")
    assert len(repo.list_activities()) == 2
    assert repo.coverage()["possible_duplicates"] == 1


def test_explicit_activity_id_links_summary_and_fit(repo, tmp_path, fit_bytes):
    from garmin_running.domain import ActivityData

    with repo.engine.begin() as conn:
        entity = repo.save(conn, ActivityData(None, "unknown"), b"summary", "summary", "42")
    path = tmp_path / "single.fit"
    path.write_bytes(fit_bytes)
    assert Importer(repo).import_path(path, activity_id="42").imported == 1
    assert repo.list_activities()[0]["id"] == entity
    assert len(repo.list_activities()) == 1


def test_audit_persists_import_errors(repo, tmp_path):
    path = tmp_path / "bad.fit"
    path.write_bytes(b"invalid")
    assert Importer(repo).import_path(path).errors
    assert repo.coverage()["imports"][0]["report"]["errors"]


def test_archive_integrity_check(repo, fit_bytes):
    _, relative = repo.archive(fit_bytes)
    (repo.data_dir / relative).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integritat"):
        repo.archive(fit_bytes)


def test_sqlite_persists_across_connections(repo, fit_bytes):
    from garmin_running.storage.repository import Repository

    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(fit_bytes), fit_bytes, "fit_export")
    second = Repository(str(repo.engine.url), repo.data_dir)
    try:
        assert second.coverage()["activities"] == 1
        assert second.coverage()["oldest"] == parse_fit(fit_bytes).start
    finally:
        second.engine.dispose()


def test_summary_units_are_not_assumed():
    data = summary_data({"distance": 500000, "duration": 2000000})
    assert data.metrics == {}
    assert data.messages[0]["original"]["distance"] == 500000


def test_local_fit_time_is_not_labelled_utc():
    from garmin_running.fit.parser import scalar

    local = datetime(2025, 1, 1, 12)
    assert scalar(local) == "2025-01-01T12:00:00"


def test_offline_reimport_keeps_api_enrichment(repo, fit_bytes):
    enriched = parse_fit(fit_bytes)
    enriched.messages.append({"name": "api_detail", "original": {"name": "synthetic"}})
    with repo.engine.begin() as conn:
        repo.save(conn, enriched, fit_bytes, "personal_api", "42")
        repo.save(conn, parse_fit(fit_bytes), fit_bytes, "fit_export")
    assert repo.list_activities()[0]["current"]["messages"][-1]["name"] == "api_detail"


@pytest.mark.parametrize("kind", ["foreign", "incompatible"])
def test_existing_database_is_rejected_without_schema_mutation(tmp_path, kind):
    import sqlite3

    from garmin_running.storage.repository import Repository

    database = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE sentinel (value TEXT)")
        conn.execute("INSERT INTO sentinel VALUES ('synthetic')")
        if kind == "incompatible":
            conn.execute("CREATE TABLE schema_version (version TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO schema_version VALUES ('999')")
    before = database.read_bytes()
    with pytest.raises(ValueError, match="migració"):
        Repository(f"sqlite:///{database}", tmp_path / "private")
    assert database.read_bytes() == before
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT value FROM sentinel").fetchone()[0] == "synthetic"
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='activities'").fetchall()


def test_sqlite_backup_and_archive_restore_preserve_history(repo, fit_bytes, tmp_path):
    import shutil
    import sqlite3

    from garmin_running.storage.repository import Repository, digest

    modified = synthetic_fit(distance=600000)
    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(fit_bytes), fit_bytes, "fit_export", "42")
        repo.save(conn, parse_fit(modified), modified, "fit_export", "42")
    repo.engine.dispose()  # Escriptors aturats durant la còpia conjunta.
    backup = tmp_path / "backup.sqlite3"
    with sqlite3.connect(repo.engine.url.database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    restored_dir = tmp_path / "restored"
    shutil.copytree(repo.data_dir, restored_dir)
    restored_db = restored_dir / "analytics.sqlite3"
    shutil.copyfile(backup, restored_db)
    restored = Repository(f"sqlite:///{restored_db}", restored_dir)
    try:
        assert restored.list_activities() == repo.list_activities()
        with restored.engine.connect() as conn:
            history = conn.execute(select(versions)).mappings().all()
            assert len(history) == 2
            for version in history:
                original = restored.data_dir / version["original_path"]
                assert original.exists()
                assert digest(original.read_bytes()) == original.name
        with sqlite3.connect(restored_db) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        restored.engine.dispose()
