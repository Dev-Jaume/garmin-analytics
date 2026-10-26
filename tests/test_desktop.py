"""Windows i treball local: sense credencials reals ni xarxa."""

import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from conftest import synthetic_fit
from sqlalchemy import select
from test_sync_recovery import Catalogue

from garmin_running.desktop.controller import DesktopController
from garmin_running.desktop.credentials import CredentialUnavailable, WindowsCredentials
from garmin_running.desktop.launcher import streamlit_command
from garmin_running.desktop.local import LocalPaths, Preferences, windows_data_path
from garmin_running.desktop.views import summary_frame, training_totals
from garmin_running.fit.parser import parse_fit
from garmin_running.physiology.friel import NAMES, heart_rate_zones, time_in_zones, zone_of
from garmin_running.storage.repository import Repository, activity_index
from garmin_running.vdot.vdot_engine import current_performance, equivalent_seconds, vdot


class MemoryCredentials:
    def __init__(self):
        self.calls = 0

    def get(self):
        self.calls += 1
        return "synthetic-key"


def local_controller(tmp_path, server=None, contract=True):
    paths = LocalPaths(tmp_path / "local").ensure()
    credentials = MemoryCredentials()
    server = server or Catalogue()
    controller = DesktopController(
        paths,
        credentials=credentials,
        client_factory=lambda *_args, **_kwargs: server.client(max_retries=0),
        contract_validated=contract,
    )
    controller.preferences.save({"consent": True, "auto_sync": True, "credential_configured": True})
    return controller, server, credentials


def finish(controller):
    controller.thread.join(timeout=10)
    assert not controller.thread.is_alive()
    assert controller.snapshot().phase == "idle"


def test_contract_blocks_before_reading_any_credential(tmp_path):
    controller, server, credentials = local_controller(tmp_path, contract=False)
    assert not controller.start_sync()
    assert credentials.calls == 0
    assert not server.requests
    assert "contracte" in controller.snapshot().message


@pytest.mark.parametrize("setting", ["consent", "credential_configured"])
def test_start_without_consent_or_credentials(tmp_path, setting):
    controller, server, credentials = local_controller(tmp_path)
    controller.preferences.save({setting: False})
    assert not controller.start_sync()
    assert credentials.calls == 0
    assert not server.requests


def test_automatic_sync_runs_once_across_reruns(tmp_path):
    controller, server, _ = local_controller(tmp_path)
    assert controller.maybe_auto_start()
    finish(controller)
    for _ in range(5):
        assert not controller.maybe_auto_start()
    assert server.downloads == {1: 1, 2: 1}
    state = controller.snapshot()
    assert state.new == 2 and state.updated == 0
    assert state.last_sync and state.outcome == "exhausted"
    assert controller.start_sync()  # El lock s'ha alliberat des del fil de treball.
    finish(controller)
    assert server.downloads == {1: 1, 2: 1}


def test_offline_and_auth_errors_keep_local_history(tmp_path):
    controller, server, _ = local_controller(tmp_path)
    repo = Repository(controller.paths.database_url, controller.paths.root)
    raw = synthetic_fit(serial=999)
    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(raw), raw, "synthetic")

    def offline(request):
        raise httpx.ConnectError("synthetic private error", request=request)

    server.fail = offline
    assert controller.start_sync()
    finish(controller)
    assert len(repo.summaries()) == 1
    assert controller.snapshot().errors == 1
    repo.engine.dispose()


def test_auth_rejection_is_safe(tmp_path):
    controller, _server, _ = local_controller(tmp_path)
    from garmin_running.garmin.client import GarminClient

    controller.client_factory = lambda *_a, **_k: GarminClient(
        "synthetic",
        approved=True,
        contract_verified=True,
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="private-do-not-log")),
        sleep=lambda _s: None,
    )
    assert controller.start_sync()
    finish(controller)
    assert controller.snapshot().errors == 1
    for handler in controller.logger.handlers:
        handler.flush()
    assert "private-do-not-log" not in (controller.paths.root / "logs/events.log").read_text()


def test_ui_reads_and_second_controller_cannot_write_during_download(tmp_path):
    controller, server, _ = local_controller(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def wait(request):
        if request.url.path.endswith("/activity/2"):
            entered.set()
            assert release.wait(5)

    server.fail = wait
    assert controller.start_sync()
    assert entered.wait(5)
    second = DesktopController(
        controller.paths,
        credentials=MemoryCredentials(),
        contract_validated=True,
        client_factory=lambda *_a, **_k: server.client(max_retries=0),
    )
    assert not second.start_sync()
    repo = Repository(controller.paths.database_url, controller.paths.root)
    assert repo.summaries() == []  # La pàgina és atòmica i la lectura no es bloqueja.
    repo.engine.dispose()
    release.set()
    finish(controller)
    assert second.start_sync() is True
    second.cancel()
    finish(second)


def test_cancel_and_restart_resumes_staging_without_data_loss(tmp_path):
    controller, server, _ = local_controller(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def wait(request):
        if request.url.path == "/download-service/files/activity/2":
            entered.set()
            assert release.wait(5)

    server.fail = wait
    assert controller.start_sync()
    assert entered.wait(5)
    controller.cancel()
    release.set()
    finish(controller)
    assert controller.snapshot().outcome == "interrupted"
    server.fail = None
    resumed = DesktopController(
        controller.paths,
        credentials=MemoryCredentials(),
        contract_validated=True,
        client_factory=lambda *_a, **_k: server.client(max_retries=0),
    )
    assert resumed.start_sync()
    finish(resumed)
    assert resumed.snapshot().outcome == "exhausted"
    assert server.downloads == {1: 1, 2: 1}
    repo = Repository(controller.paths.database_url, controller.paths.root)
    assert len(repo.summaries()) == 2
    assert resumed.snapshot().last_sync
    repo.engine.dispose()


def test_windows_paths_with_spaces():
    path = windows_data_path(r"C:\Users\Nom amb espais\AppData\Local")
    assert str(path).endswith(r"AppData\Local\GarminRunningAnalytics")
    assert (
        str(windows_data_path(r"C:\Users\User", r"D:\Dades privades\Garmin"))
        == r"D:\Dades privades\Garmin"
    )
    with pytest.raises(ValueError):
        windows_data_path("relative")


def test_preferences_cannot_store_api_key(tmp_path):
    prefs = Preferences(LocalPaths(tmp_path).ensure())
    with pytest.raises(ValueError):
        prefs.save({"api_key": "synthetic"})
    prefs.save({"consent": True})
    assert "api_key" not in prefs.path.read_text()
    assert prefs.load()["consent"]


def test_vault_is_explicit_and_does_not_log_secret(tmp_path):
    class Vault:
        def set_password(self, service, account, value):
            self.value = value

        def get_password(self, service, account):
            return self.value

        def delete_password(self, service, account):
            self.value = None

    backend = Vault()
    credentials = WindowsCredentials(backend)
    credentials.save("synthetic-only")
    assert credentials.get() == "synthetic-only"
    credentials.delete()
    assert credentials.get() is None

    class Failing:
        def set_password(self, *_args):
            raise RuntimeError("synthetic-secret-do-not-print")

    with pytest.raises(CredentialUnavailable) as exc:
        WindowsCredentials(Failing()).save("synthetic-only")
    assert "synthetic-secret" not in str(exc.value)


def test_launcher_enforces_loopback_and_telemetry_off():
    command = streamlit_command(8501)
    assert "--server.address=127.0.0.1" in command
    assert "--browser.gatherUsageStats=false" in command
    assert "--server.enableXsrfProtection=true" in command
    with pytest.raises(ValueError):
        streamlit_command(80)


def test_schema1_migration_and_lightweight_index(tmp_path):
    path = tmp_path / "history.sqlite3"
    repo = Repository(f"sqlite:///{path}", tmp_path)
    raw = synthetic_fit()
    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(raw), raw, "synthetic")
    payload_before = repo.list_activities()
    repo.engine.dispose()
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE activity_index")
        conn.execute("UPDATE schema_version SET version='1'")
    restored = Repository(f"sqlite:///{path}", tmp_path)
    rows = restored.summaries()
    assert len(rows) == 1
    assert "samples" not in rows[0] and "messages" not in rows[0]
    assert restored.list_activities() == payload_before
    with restored.engine.connect() as conn:
        assert conn.execute(select(activity_index.c.metrics)).scalar_one()["distance_m"] == 5000
    restored.engine.dispose()


def test_friel_integer_zones_have_no_gaps_or_overlaps():
    zones = heart_rate_zones(170)
    for bpm in range(0, 301):
        assert zone_of(bpm, zones) in NAMES
        assert (
            sum(
                bpm >= z["Des de BPM"] and (z["Fins a BPM"] is None or bpm <= z["Fins a BPM"])
                for z in zones
            )
            == 1
        )
    assert zone_of(144, zones) == "Z1"
    assert zone_of(145, zones) == "Z2"
    assert zone_of(170, zones) == "Z5a"
    assert zone_of(181, zones) == "Z5c"


def test_zone_duration_excludes_gap_and_pause():
    activity = {
        "samples": [
            {"timestamp": "2026-01-01T00:00:00+00:00", "heart_rate": 150},
            {"timestamp": "2026-01-01T00:00:03+00:00", "heart_rate": 150},
            {"timestamp": "2026-01-01T00:00:23+00:00", "heart_rate": 150},
            {"timestamp": "2026-01-01T00:00:26+00:00", "heart_rate": 150},
        ],
        "events": [
            {"timestamp": "2026-01-01T00:00:23+00:00", "event": "timer", "event_type": "stop_all"}
        ],
    }
    result = time_in_zones(activity, 170)
    assert result["seconds"]["Z2"] == 3
    assert result["excluded_seconds"] == 23


def test_vdot_equations_reference_and_inverse():
    assert vdot(5000, 1200) == pytest.approx(49.806, abs=0.001)
    assert equivalent_seconds(vdot(5000, 1200), 5000) == pytest.approx(1200)
    assert equivalent_seconds(vdot(5000, 1200), 10000) == pytest.approx(2487, abs=2)
    with pytest.raises(ValueError):
        vdot(5000, -1)


def test_current_vdot_uses_recent_validated_result_not_old_best():
    today = date(2026, 10, 26)
    races = [
        {"id": "old", "date": "2020-01-01", "validated": True},
        {"id": "recent", "date": (today - timedelta(days=3)).isoformat(), "validated": True},
        {"id": "future", "date": (today + timedelta(days=3)).isoformat(), "validated": True},
    ]
    assert current_performance(races, today)["id"] == "recent"
    assert current_performance([races[0]], today) is None


def test_summary_does_not_read_fit_and_pace_is_weighted():
    rows = [
        {
            "id": "one",
            "start": "2026-01-01T00:00:00+00:00",
            "sport": "running",
            "metrics": {"distance_m": 1000, "timer_s": 300},
            "flags": [],
        },
        {
            "id": "two",
            "start": "2026-01-02T00:00:00+00:00",
            "sport": "running",
            "metrics": {"distance_m": 2000, "timer_s": 800},
            "flags": [],
        },
    ]
    totals = training_totals(summary_frame(rows))
    assert totals["pace"] == pytest.approx(1100 / 3)
    assert totals["km"] == 3


def test_streamlit_pages_offline(tmp_path, monkeypatch, fit_bytes):
    monkeypatch.setenv("GRA_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    paths = LocalPaths.discover().ensure()
    repo = Repository(paths.database_url, paths.root)
    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(fit_bytes), fit_bytes, "synthetic")
    activity_id = repo.summaries()[0]["id"]
    Preferences(paths).save(
        {
            "thresholds": [
                {"bpm": 170, "date": date.today().isoformat(), "source": "Fixture sintètica"}
            ],
            "races": [
                {
                    "id": "synthetic",
                    "activity_id": activity_id,
                    "date": date.today().isoformat(),
                    "distance_m": 5000,
                    "seconds": 1200,
                    "validated": True,
                }
            ],
        }
    )
    repo.engine.dispose()
    from streamlit.testing.v1 import AppTest

    import garmin_running.desktop

    app_file = Path(garmin_running.desktop.__file__).with_name("app.py")
    app = AppTest.from_file(str(app_file)).run(timeout=30)
    assert not app.exception
    for page in [
        "Historial",
        "Detall d'activitat",
        "Joe Friel",
        "Jack Daniels VDOT",
        "Qualitat de dades",
        "Configuració",
        "Resum",
    ]:
        app.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not app.exception, page
        if page == "Jack Daniels VDOT":
            checkbox = next(c for c in app.checkbox if "Mostra estimacions" in c.label)
            checkbox.check().run(timeout=30)
            assert not app.exception


def test_empty_dashboard_without_network_or_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("GRA_DATA_DIR", str(tmp_path / "empty-app"))
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    def forbidden(_self):
        raise AssertionError("No s'ha de consultar la clau en iniciar offline")

    monkeypatch.setattr(WindowsCredentials, "get", forbidden)
    from streamlit.testing.v1 import AppTest

    import garmin_running.desktop

    app_file = Path(garmin_running.desktop.__file__).with_name("app.py")
    app = AppTest.from_file(str(app_file)).run(timeout=30)
    assert not app.exception
    assert any("Encara no hi ha activitats" in entry.value for entry in app.info)
    app.run(timeout=30)
    assert not app.exception


def test_local_backup_restores_full_database_and_originals(tmp_path):
    controller, _, _ = local_controller(tmp_path)
    repo = Repository(controller.paths.database_url, controller.paths.root)
    raw = synthetic_fit()
    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(raw), raw, "synthetic")
    before = repo.list_activities()
    repo.engine.dispose()
    assert controller.start_backup()
    finish(controller)
    assert controller.snapshot().outcome == "backed_up"
    snapshot = next((controller.paths.root / "backups").iterdir())
    restored = Repository(f"sqlite:///{snapshot / 'analytics.sqlite3'}", snapshot)
    assert restored.list_activities() == before
    assert len(restored.summaries()) == 1
    assert (snapshot / "settings.json").exists()
    assert not (snapshot / "writer.lock").exists()
    restored.engine.dispose()


def test_training_estimates_units_ranges_and_interval_duration_filters():
    from garmin_running.vdot.vdot_engine import interval_estimates, training_estimates

    score = vdot(5000, 1200)
    paces = training_estimates(score)
    assert [p["type"] for p in paces] == ["E", "M", "T", "I", "R"]
    for p in paces:
        assert p["fast_s_per_km"] <= p["slow_s_per_km"]
        assert p["fast_kmh"] * p["fast_s_per_km"] == pytest.approx(3600)
    marathon = next(p for p in paces if p["type"] == "M")
    assert marathon["fast_s_per_km"] * 42.195 == pytest.approx(equivalent_seconds(score, 42195))
    reps = interval_estimates(paces)
    assert all(r["Tipus"] not in {"E", "M"} for r in reps)
    assert all(
        180 <= r["Temps ràpid s"] <= r["Temps lent s"] <= 300 for r in reps if r["Tipus"] == "I"
    )
    assert all(r["Temps lent s"] <= 120 for r in reps if r["Tipus"] == "R")


def test_real_windows_vault_with_synthetic_test_entry():
    import sys
    from uuid import uuid4

    if sys.platform != "win32":
        pytest.skip("Windows Credential Manager només es pot provar a Windows")
    from keyring.backends.Windows import WinVaultKeyring

    backend = WinVaultKeyring()
    service = f"GarminRunningAnalytics.Tests.{uuid4()}"
    try:
        backend.set_password(service, "synthetic", "synthetic-only-not-a-garmin-key")
        assert backend.get_password(service, "synthetic") == "synthetic-only-not-a-garmin-key"
    finally:
        backend.delete_password(service, "synthetic")


def test_cli_flags_cannot_bypass_contract_guard(tmp_path, monkeypatch):
    import sys

    from garmin_running.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["gra", "--data-dir", str(tmp_path), "sync", "--secrets-approved", "--contract-verified"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not (tmp_path / "analytics.sqlite3").exists()


def test_thousands_of_summaries_do_not_fetch_sample_payloads(tmp_path):
    from sqlalchemy import event, insert

    from garmin_running.storage.repository import activities

    repo = Repository(f"sqlite:///{tmp_path / 'large.sqlite3'}", tmp_path)
    with repo.engine.begin() as conn:
        conn.execute(
            insert(activities),
            [
                {
                    "id": str(i),
                    "current": {"samples": [{"timestamp": "synthetic", "heart_rate": 100}] * 50},
                }
                for i in range(2000)
            ],
        )
        conn.execute(
            insert(activity_index),
            [
                {
                    "id": str(i),
                    "start": "2026-01-01T00:00:00+00:00",
                    "sport": "running",
                    "metrics": {"distance_m": 1000, "timer_s": 300},
                    "flags": [],
                }
                for i in range(2000)
            ],
        )
    statements = []
    event.listen(
        repo.engine,
        "before_cursor_execute",
        lambda _c, _cursor, statement, *_rest: statements.append(statement),
    )
    assert len(repo.summaries(limit=100, offset=1900)) == 100
    assert all("activities.current" not in query for query in statements)
    assert len(repo.summaries()) == 2000
    repo.engine.dispose()


def test_large_directory_import_budget_is_per_file(repo, fit_bytes, tmp_path):
    from garmin_running.ingestion.importer import Importer

    folder = tmp_path / "files"
    folder.mkdir()
    (folder / "a.fit").write_bytes(fit_bytes)
    (folder / "b.fit").write_bytes(synthetic_fit(serial=12346))
    report = Importer(repo, max_total_bytes=len(fit_bytes) + 20).import_path(folder)
    assert report.imported == 2
    assert not report.errors


def test_invalid_settings_open_with_network_consent_disabled(tmp_path):
    prefs = Preferences(LocalPaths(tmp_path).ensure())
    prefs.path.write_text("invalid-json")
    assert prefs.load()["consent"] is False
    assert prefs.error is True
    prefs.path.write_text('{"consent": "false", "auto_sync": "false"}')
    assert prefs.load()["consent"] is False
    assert prefs.load()["auto_sync"] is False


def test_sync_counts_existing_offline_import_as_updated_not_new(tmp_path):
    controller, _, _ = local_controller(tmp_path)
    repo = Repository(controller.paths.database_url, controller.paths.root)
    raw = synthetic_fit(serial=1, distance=100000)
    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(raw), raw, "fit_export")
    assert controller.start_sync()
    finish(controller)
    assert controller.snapshot().new == 1
    assert controller.snapshot().updated == 1
    assert len(repo.summaries()) == 2
    repo.engine.dispose()


def test_missing_metrics_do_not_become_zero_personal_measurements():
    rows = [
        {
            "id": "unknown",
            "start": "2026-01-01T00:00:00+00:00",
            "sport": "running",
            "metrics": {},
            "flags": ["summary_only"],
        }
    ]
    totals = training_totals(summary_frame(rows))
    assert totals["km"] is None
    assert totals["hours"] is None
    assert totals["pace"] is None


def test_filtered_history_can_keep_undated_activities(repo):
    from garmin_running.domain import ActivityData

    with repo.engine.begin() as conn:
        repo.save(
            conn,
            ActivityData(None, "running", flags=["missing_start"]),
            b"synthetic-undated",
            "synthetic",
        )
    assert repo.summaries(start="2026-01-01", end="2026-02-01") == []
    assert len(repo.summaries(start="2026-01-01", end="2026-02-01", include_undated=True)) == 1


def test_revoking_consent_cancels_current_worker_and_prevents_next_start(tmp_path):
    controller, server, _ = local_controller(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def wait(request):
        if request.url.path == "/activity-service/activity/2":
            entered.set()
            assert release.wait(5)

    server.fail = wait
    assert controller.start_sync()
    assert entered.wait(5)
    controller.configure_consent(False, True)
    release.set()
    finish(controller)
    assert controller.snapshot().outcome == "interrupted"
    assert not controller.preferences.load()["auto_sync"]
    assert not controller.start_sync()
