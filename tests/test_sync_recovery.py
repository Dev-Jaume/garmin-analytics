"""Interrupcions de xarxa/disc/SQL i catàleg mutable, només amb dades sintètiques."""

import json
from collections import Counter

import httpx
import pytest
from conftest import synthetic_fit
from sqlalchemy import event, select
from test_garmin import MockGarmin
from test_ingestion import zipped

from garmin_running.domain import DataError
from garmin_running.garmin.client import SEARCH_PATH, TOKEN_PATH, GarminError
from garmin_running.garmin.sync import Synchronizer
from garmin_running.storage.repository import sync_runs, versions


class Catalogue(MockGarmin):
    def __init__(self, pages=None):
        super().__init__(synthetic_fit())
        self.pages = pages or {0: [1, 2]}
        self.downloads = Counter()
        self.fail = None
        self.before_http = lambda: None

    def handle(self, request):
        self.before_http()
        if request.url.path == TOKEN_PATH:
            return super().handle(request)
        if self.fail:
            self.fail(request)
        if request.url.path == SEARCH_PATH:
            offset = int(request.url.params["start"])
            values = self.pages(offset) if callable(self.pages) else self.pages.get(offset, [])
            return httpx.Response(
                200, json=[v if isinstance(v, dict) else {"activityId": v} for v in values]
            )
        activity_id = int(request.url.path.rsplit("/", 1)[1])
        if "/download-service/" in request.url.path:
            self.downloads[activity_id] += 1
            assert "application/zip" in request.headers["Accept"]
            return httpx.Response(
                200,
                content=zipped(
                    {
                        "original.fit": synthetic_fit(
                            serial=activity_id, distance=activity_id * 100000
                        )
                    }
                ),
            )
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"activityId": activity_id})


def run_row(repo):
    with repo.engine.connect() as conn:
        return dict(conn.execute(select(sync_runs)).mappings().one())


def assert_originals(repo):
    with repo.engine.connect() as conn:
        history = conn.execute(select(versions)).mappings().all()
    for version in history:
        assert (repo.data_dir / version["original_path"]).exists()
    return len(history)


def test_no_sql_transaction_during_any_http_request(repo):
    active = set()
    event.listen(repo.engine, "begin", lambda c: active.add(id(c)))
    event.listen(repo.engine, "commit", lambda c: active.discard(id(c)))
    event.listen(repo.engine, "rollback", lambda c: active.discard(id(c)))
    server = Catalogue()
    calls = []

    def verify():
        assert not active, "HTTP s'ha executat amb transacció SQL oberta"
        calls.append(True)

    server.before_http = verify
    client = server.client()
    try:
        Synchronizer(client, repo).run(page_size=2)
        assert len(calls) >= 9  # Token, dues lectures de catàleg, detalls i ZIP.
        assert run_row(repo)["status"] == "exhausted"
        assert assert_originals(repo) == 2
    finally:
        client.close()


def test_network_failure_after_first_download_resume_reuses_stage(repo):
    server = Catalogue()

    def fail(request):
        if request.url.path == "/activity-service/activity/2":
            raise httpx.ConnectError("synthetic network failure", request=request)

    server.fail = fail
    client = server.client(max_retries=0)
    sync = Synchronizer(client, repo)
    with pytest.raises(GarminError):
        sync.run(page_size=2)
    row = run_row(repo)
    assert row["next_offset"] == 0
    assert row["audit"]["failure_log"][-1]["phase"] == "prepare"
    assert repo.list_activities() == []
    assert len(list((repo.data_dir / "staging").rglob("*.json"))) == 1
    server.fail = None
    sync.run(resume=row["id"], page_size=2)
    assert server.downloads == {1: 1, 2: 1}
    assert len(repo.list_activities()) == assert_originals(repo) == 2
    assert run_row(repo)["audit"]["resume_log"][0]["strategy"] == "restart_from_zero"
    client.close()


def test_failure_between_download_and_archive_can_retry(repo, monkeypatch):
    server = Catalogue({0: [1]})
    client = server.client()
    archive = repo.archive

    def disk_failure(_raw):
        raise OSError("synthetic disk unavailable")

    monkeypatch.setattr(repo, "archive", disk_failure)
    sync = Synchronizer(client, repo)
    with pytest.raises(OSError):
        sync.run(page_size=1)
    row = run_row(repo)
    assert row["next_offset"] == 0
    assert repo.list_activities() == []
    monkeypatch.setattr(repo, "archive", archive)
    sync.run(resume=row["id"], page_size=1)
    assert server.downloads[1] == 2  # Sense manifest complet cal tornar a descarregar.
    assert assert_originals(repo) == 1
    client.close()


def test_database_failure_rolls_back_page_and_resume_uses_both_stages(repo, monkeypatch):
    server = Catalogue()
    client = server.client()
    save = repo.save_archived

    def fail_second(conn, data, sha, path, source, activity_id=None):
        if activity_id == "2":
            raise RuntimeError("synthetic persistence failure")
        return save(conn, data, sha, path, source, activity_id)

    monkeypatch.setattr(repo, "save_archived", fail_second)
    sync = Synchronizer(client, repo)
    with pytest.raises(RuntimeError):
        sync.run(page_size=2)
    row = run_row(repo)
    assert row["next_offset"] == row["pages"] == 0
    assert row["audit"]["summary_hashes"] == {}
    assert repo.list_activities() == []
    assert assert_originals(repo) == 0
    monkeypatch.setattr(repo, "save_archived", save)
    sync.run(resume=row["id"], page_size=2)
    assert server.downloads == {1: 1, 2: 1}
    assert len(repo.list_activities()) == assert_originals(repo) == 2
    client.close()


def test_keyboard_interrupt_mid_page_is_recoverable(repo):
    server = Catalogue()

    def interrupt(request):
        if request.url.path == "/download-service/files/activity/2":
            raise KeyboardInterrupt

    server.fail = interrupt
    client = server.client()
    sync = Synchronizer(client, repo)
    with pytest.raises(KeyboardInterrupt):
        sync.run(page_size=2)
    row = run_row(repo)
    assert row["status"] == "interrupted"
    assert row["next_offset"] == 0
    assert repo.list_activities() == []
    server.fail = None
    sync.run(resume=row["id"], page_size=2)
    assert server.downloads == {1: 1, 2: 1}
    assert assert_originals(repo) == 2
    client.close()


def test_failure_after_committed_page_keeps_checkpoint(repo):
    server = Catalogue({0: [1], 1: [2]})

    def fail(request):
        if request.url.path == SEARCH_PATH and request.url.params["start"] == "1":
            raise httpx.ReadError("synthetic interrupted page boundary", request=request)

    server.fail = fail
    client = server.client(max_retries=0)
    sync = Synchronizer(client, repo)
    with pytest.raises(GarminError):
        sync.run(page_size=1)
    row = run_row(repo)
    assert row["next_offset"] == row["pages"] == 1
    assert len(repo.list_activities()) == assert_originals(repo) == 1
    server.fail = None
    sync.run(resume=row["id"], page_size=1)
    assert server.downloads == {1: 1, 2: 1}
    assert run_row(repo)["status"] == "exhausted"
    assert assert_originals(repo) == 2
    client.close()


@pytest.mark.parametrize("damage", ["manifest", "original"])
def test_corrupt_stage_never_enters_database(repo, damage):
    server = Catalogue()
    client = server.client()
    sync = Synchronizer(client, repo)
    server.fail = lambda r: (
        (_ for _ in ()).throw(KeyboardInterrupt())
        if (r.url.path == "/activity-service/activity/2")
        else None
    )
    with pytest.raises(KeyboardInterrupt):
        sync.run(page_size=2)
    row = run_row(repo)
    path = next((repo.data_dir / "staging").rglob("*.json"))
    manifest = json.loads(path.read_bytes())
    if damage == "manifest":
        manifest["body"]["activity_id"] = "999"
        path.write_text(json.dumps(manifest))
    else:
        sha = manifest["body"]["refs"]["fit"]
        (repo.data_dir / "originals" / sha[:2] / sha).unlink()
    server.fail = None
    with pytest.raises(DataError, match="Staging"):
        sync.run(resume=row["id"], page_size=2)
    assert repo.list_activities() == []
    assert run_row(repo)["next_offset"] == 0
    client.close()


def test_identical_duplicate_in_page_is_audited_not_downloaded_twice(repo):
    server = Catalogue({0: [1, 1]})
    client = server.client()
    Synchronizer(client, repo).run(page_size=2)
    row = run_row(repo)
    assert row["status"] == "unstable"
    assert row["audit"]["issues"][0]["within_page_duplicates"] == ["1"]
    assert server.downloads == {1: 1}
    assert assert_originals(repo) == 1
    client.close()


def test_conflicting_duplicate_rejected_before_any_download(repo):
    server = Catalogue({0: [{"activityId": 1, "name": "a"}, {"activityId": 1, "name": "b"}]})
    client = server.client()
    with pytest.raises(GarminError, match="duplicat"):
        Synchronizer(client, repo).run(page_size=2)
    assert not server.downloads
    assert run_row(repo)["audit"]["issues"][-1]["code"] == "conflicting_duplicate"
    assert repo.list_activities() == []
    client.close()


def test_head_insertion_detects_overlap_and_omitted_new_id(repo):
    calls = 0

    def mutable(offset):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [1, 2]
        return {0: [4, 1], 2: [2, 3]}.get(offset, [])

    server = Catalogue(mutable)
    client = server.client()
    Synchronizer(client, repo).run(page_size=2)
    row = run_row(repo)
    assert row["status"] == "unstable"
    assert any(i.get("cross_page_duplicates") == ["2"] for i in row["audit"]["issues"])
    assert row["audit"]["reconciliation"]["new_ids"] == ["4"]
    assert row["audit"]["reconciliation"]["sequence_changed"]
    assert len(repo.list_activities()) == 3
    client.close()


def test_deletion_during_scan_exposes_possible_middle_omission(repo):
    calls = 0

    def mutable(offset):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [1, 2]
        return {0: [1, 3], 2: [4]}.get(offset, [])

    server = Catalogue(mutable)
    client = server.client()
    Synchronizer(client, repo).run(page_size=2)
    result = run_row(repo)["audit"]["reconciliation"]
    assert result["new_ids"] == ["3"]
    assert result["missing_ids"] == ["2"]
    assert run_row(repo)["status"] == "unstable"
    assert len(repo.list_activities()) == 3  # No esborra automàticament l'activitat 2.
    client.close()


def test_network_error_in_reconciliation_resume_preserves_downloads(repo):
    server = Catalogue({0: [1]})
    searches = 0

    def fail(request):
        nonlocal searches
        if request.url.path == SEARCH_PATH:
            searches += 1
            if searches == 3:
                raise httpx.ReadError("synthetic verification error", request=request)

    server.fail = fail
    client = server.client(max_retries=0)
    sync = Synchronizer(client, repo)
    with pytest.raises(GarminError):
        sync.run(page_size=1)
    row = run_row(repo)
    assert row["audit"]["failure_log"][-1]["phase"] == "reconcile"
    assert len(repo.list_activities()) == 1
    server.fail = None
    sync.run(resume=row["id"], page_size=1)
    assert server.downloads == {1: 1}
    assert run_row(repo)["status"] == "exhausted"
    client.close()


def test_reconciliation_page_limit_marks_run_incomplete(repo):
    calls = 0

    def growing(offset):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return [1] if offset == 0 else []
        return {0: [1], 1: [2]}.get(offset, [])

    server = Catalogue(growing)
    client = server.client()
    Synchronizer(client, repo).run(page_size=1, max_pages=2)
    result = run_row(repo)
    assert result["status"] == "unstable"
    assert not result["audit"]["reconciliation"]["complete"]
    assert result["audit"]["reconciliation"]["new_ids"] == ["2"]
    client.close()


def test_noncontiguous_global_ids_are_not_treated_as_missing_activities(repo):
    server = Catalogue({0: [1, 1000]})
    client = server.client()
    Synchronizer(client, repo).run(page_size=2)
    assert run_row(repo)["status"] == "exhausted"
    assert not run_row(repo)["audit"]["issues"]
    client.close()


def test_changed_summary_between_passes_is_detected(repo):
    calls = 0

    def changing(offset):
        nonlocal calls
        calls += 1
        return (
            [{"activityId": 1, "name": "before" if calls == 1 else "after"}] if offset == 0 else []
        )

    server = Catalogue(changing)
    client = server.client()
    Synchronizer(client, repo).run(page_size=1)
    assert run_row(repo)["status"] == "unstable"
    assert run_row(repo)["audit"]["reconciliation"]["changed_summary_ids"] == ["1"]
    client.close()


def test_previous_inventory_disappearance_is_audited_without_deleting(repo):
    raw = synthetic_fit(serial=99)
    from garmin_running.fit.parser import parse_fit

    with repo.engine.begin() as conn:
        repo.save(conn, parse_fit(raw), raw, "synthetic", "99")
    server = Catalogue({0: [1]})
    client = server.client()
    Synchronizer(client, repo).run(page_size=1)
    assert run_row(repo)["audit"]["reconciliation"]["not_seen_since_previous_inventory"] == ["99"]
    assert len(repo.list_activities()) == 2
    client.close()
