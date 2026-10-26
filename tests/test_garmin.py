import json

import httpx
import pytest
from conftest import synthetic_fit, synthetic_jwt
from sqlalchemy import select

from garmin_running.garmin.client import SEARCH_PATH, TOKEN_PATH, GarminClient, GarminError
from garmin_running.garmin.sync import Synchronizer, downloaded_fit
from garmin_running.storage.repository import sync_runs


class MockGarmin:
    def __init__(self, fit_bytes):
        self.fit = fit_bytes
        self.requests = []
        self.tokens = 0
        self.now = 0
        self.sleeps = []

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration

    def handle(self, request):
        self.requests.append(request)
        if request.url.path == TOKEN_PATH:
            self.tokens += 1
            assert request.headers["Authorization"] == "ApiKey synthetic-key"
            return httpx.Response(
                200, text=synthetic_jwt(1_800_000_000 + self.now + 100, jti=self.tokens)
            )
        assert request.headers["Authorization"].startswith("Bearer eyJ")
        if request.url.path == SEARCH_PATH:
            start = int(request.url.params["start"])
            return httpx.Response(200, json=[{"activityId": 1}] if start == 0 else [])
        if "/download-service/" in request.url.path:
            return httpx.Response(200, content=self.fit)
        return httpx.Response(200, json={"activityId": 1})

    def client(self, handler=None, **kwargs):
        return GarminClient(
            "synthetic-key",
            approved=True,
            contract_verified=True,
            transport=httpx.MockTransport(handler or self.handle),
            sleep=self.sleep,
            clock=lambda: self.now,
            wall_clock=lambda: 1_800_000_000 + self.now,
            **kwargs,
        )


def test_no_auth_without_approval():
    with pytest.raises(GarminError, match="bloquejada"):
        GarminClient("never-sent")


def test_auth_expiry_and_rate_limit(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client()
    assert client.search(0, 2) == [{"activityId": 1}]
    assert server.tokens == 1
    client.detail("1")
    assert server.tokens == 1
    server.now += 100
    client.detail("1")
    assert server.tokens == 2
    assert any(d >= 1 for d in server.sleeps)
    assert "test-2" not in repr(client._token)
    client.close()


def test_401_refresh_once(fit_bytes):
    server = MockGarmin(fit_bytes)
    attempts = 0

    def handler(request):
        nonlocal attempts
        if request.url.path == SEARCH_PATH:
            attempts += 1
            if attempts == 1:
                return httpx.Response(401)
        return server.handle(request)

    client = server.client(handler)
    assert client.search(0, 2)
    assert server.tokens == attempts == 2
    client.close()


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retry_backoff(fit_bytes, status):
    server = MockGarmin(fit_bytes)
    attempts = 0

    def handler(request):
        nonlocal attempts
        if request.url.path == SEARCH_PATH:
            attempts += 1
            if attempts < 3:
                return httpx.Response(status, headers={"Retry-After": "2"})
        return server.handle(request)

    client = server.client(handler)
    assert client.search(0, 2)
    assert attempts == 3
    assert server.sleeps.count(2) >= 2
    client.close()


def test_no_sensitive_error_body(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(403, text="private-secret-and-health"))
    with pytest.raises(GarminError) as exc:
        client.search(0, 2)
    assert "private" not in str(exc.value)
    assert "synthetic-key" not in str(exc.value)
    client.close()


def test_transport_error_is_bounded(fit_bytes):
    server = MockGarmin(fit_bytes)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("private", request=request)

    client = server.client(handler, max_retries=2)
    with pytest.raises(GarminError, match="transport"):
        client.search(0, 2)
    assert calls == 3
    client.close()


@pytest.mark.parametrize(
    "token",
    [{}, {"access_token": "x", "expires_in": -1}, {"access_token": "x", "expires_in": "3600"}],
)
def test_unknown_token_schema_rejected(fit_bytes, token):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(200, json=token))
    with pytest.raises(GarminError):
        client.detail("1")
    client.close()


def test_redirect_not_followed(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(302, headers={"Location": "https://evil.test"}))
    with pytest.raises(GarminError, match="302"):
        client.search(0, 2)
    client.close()


def test_search_schema_rejected(fit_bytes):
    server = MockGarmin(fit_bytes)

    def handler(request):
        if request.url.path == SEARCH_PATH:
            return httpx.Response(200, json={"activities": []})
        return server.handle(request)

    client = server.client(handler)
    with pytest.raises(GarminError, match="cerca"):
        client.search(0, 2)
    client.close()


def test_pagination_incremental_and_refresh(repo, fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client()
    sync = Synchronizer(client, repo)
    run_id = sync.run(page_size=1)
    assert len(repo.list_activities()) == 1
    with repo.engine.connect() as conn:
        run = conn.execute(select(sync_runs).where(sync_runs.c.id == run_id)).mappings().one()
        assert run["status"] == "exhausted"
        assert run["pages"] == 2
        assert [p["offset"] for p in run["audit"]["page_log"]] == [0, 1]

    def downloads():
        return sum("/download-service/" in r.url.path for r in server.requests)

    assert downloads() == 1
    sync.run(page_size=1)
    assert downloads() == 1
    sync.run(page_size=1, refresh=True)
    assert downloads() == 2
    assert repo.coverage()["status"] == "Cobertura no verificada"
    client.close()


def test_failure_and_resume(repo, fit_bytes):
    server = MockGarmin(fit_bytes)
    fail = True

    def handler(request):
        if "/download-service/" in request.url.path and fail:
            return httpx.Response(403)
        return server.handle(request)

    client = server.client(handler)
    sync = Synchronizer(client, repo)
    with pytest.raises(GarminError):
        sync.run(page_size=1)
    assert repo.list_activities() == []
    with repo.engine.connect() as conn:
        run = conn.execute(select(sync_runs)).mappings().one()
        assert run["status"] == "failed"
        assert run["next_offset"] == 0
        run_id = run["id"]
    fail = False
    sync.run(resume=run_id, page_size=1)
    assert len(repo.list_activities()) == 1
    client.close()


def test_repeated_page_detected(repo, fit_bytes):
    server = MockGarmin(fit_bytes)

    def handler(request):
        if request.url.path == SEARCH_PATH:
            return httpx.Response(200, json=[{"activityId": 1}])
        return server.handle(request)

    client = server.client(handler)
    with pytest.raises(GarminError, match="repetida"):
        Synchronizer(client, repo).run(page_size=1)
    client.close()


def test_page_limit_not_marked_complete(repo, fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client()
    Synchronizer(client, repo).run(page_size=1, max_pages=1)
    with repo.engine.connect() as conn:
        assert conn.execute(select(sync_runs.c.status)).scalar_one() == "page_limit"
    client.close()


def test_zip_download(fit_bytes):
    from test_ingestion import zipped

    assert downloaded_fit(zipped({"one.fit": fit_bytes})) == fit_bytes
    with pytest.raises(ValueError):
        downloaded_fit(zipped({"one.fit": fit_bytes, "two.fit": synthetic_fit(serial=99)}))


def test_id_path_injection_rejected(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client()
    with pytest.raises(ValueError):
        client.detail("../../evil")
    assert server.requests == []
    client.close()


def test_retry_exhaustion(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(503), max_retries=1)
    with pytest.raises(GarminError, match="exhaurits"):
        client.search(0, 2)
    client.close()


def test_long_retry_after_defers_resume(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(429, headers={"Retry-After": "600"}))
    with pytest.raises(GarminError, match="reprendre"):
        client.search(0, 2)
    assert all(s <= 60 for s in server.sleeps)
    client.close()


def test_download_size_limit_is_enforced(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(200, content=b"123456789"))
    with pytest.raises(GarminError, match="mida"):
        client._request("GET", SEARCH_PATH, max_bytes=8)
    client.close()


def test_full_page_atomicity_on_second_activity_failure(repo, fit_bytes):
    server = MockGarmin(fit_bytes)

    def handler(request):
        if request.url.path == SEARCH_PATH:
            return httpx.Response(200, json=[{"activityId": 1}, {"activityId": 2}])
        if request.url.path.endswith("/2"):
            return httpx.Response(404)
        return server.handle(request)

    client = server.client(handler)
    with pytest.raises(GarminError):
        Synchronizer(client, repo).run(page_size=2)
    assert repo.list_activities() == []
    with repo.engine.connect() as conn:
        assert conn.execute(select(sync_runs.c.next_offset)).scalar_one() == 0
    client.close()


def test_expiry_renews_using_api_key_without_refresh_token(fit_bytes):
    server = MockGarmin(fit_bytes)

    def handler(request):
        if request.url.path == TOKEN_PATH:
            server.requests.append(request)
            server.tokens += 1
            return httpx.Response(
                200,
                text=synthetic_jwt(
                    1_800_000_000 + server.now + 10, refresh_token="ignore-synthetic"
                ),
            )
        return server.handle(request)

    client = server.client(handler)
    client.search(0, 2)
    server.now += 20
    client.search(0, 2)
    tokens = [r for r in server.requests if r.method == "POST"]
    assert len(tokens) == 2
    for request in tokens:
        assert request.url.path == TOKEN_PATH
        assert request.headers["Authorization"] == "ApiKey synthetic-key"
        assert request.content == b""
        assert not request.url.params
    assert not hasattr(client._token, "refresh_token")
    assert all("ignore-synthetic" not in str(r.headers) for r in server.requests)
    client.close()


def test_boolean_expiry_rejected(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(200, text=synthetic_jwt(True)))
    with pytest.raises(GarminError, match="caducitat"):
        client.detail("1")
    client.close()


@pytest.mark.parametrize(
    "value",
    [
        "not-a-jwt",
        json.dumps(synthetic_jwt()),
        synthetic_jwt(10**400),
        synthetic_jwt(0),
        synthetic_jwt("future"),
        synthetic_jwt(None),
        synthetic_jwt(float("inf")),
    ],
)
def test_invalid_plain_jwt_expiry_is_rejected(fit_bytes, value):
    server = MockGarmin(fit_bytes)
    client = server.client(lambda _: httpx.Response(200, text=value))
    with pytest.raises(GarminError, match="JWT"):
        client.detail("1")
    client.close()


def test_token_is_plain_jwt_and_resource_headers_match_official_reference(fit_bytes):
    server = MockGarmin(fit_bytes)
    client = server.client()
    client.search(0, 20)
    token_request = server.requests[0]
    search_request = server.requests[1]
    assert token_request.headers["Accept"] == "*/*"
    assert token_request.headers["Authorization"] == "ApiKey synthetic-key"
    assert search_request.headers["Accept"] == "application/json"
    assert search_request.headers["Authorization"].startswith("Bearer eyJ")
    assert dict(search_request.url.params) == {"start": "0", "limit": "20"}
    assert client._token.value not in repr(client._token)
    client.close()


@pytest.mark.parametrize("activity_id", ["0", "１２３", "-1", "1.5"])
def test_official_download_id_validation(fit_bytes, activity_id):
    server = MockGarmin(fit_bytes)
    client = server.client()
    with pytest.raises(ValueError):
        client.download(activity_id)
    assert not server.requests
    client.close()
