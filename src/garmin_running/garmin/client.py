"""Transport oficial, sense xarxa fins que l'aplicació el cridi explícitament.

Les rutes estan documentades. Els esquemes de resposta i paràmetres del perfil
provisional han de contrastar-se amb l'OpenAPI abans d'habilitar la connexió real.
"""

import base64
import binascii
import json
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
SEARCH_PATH = "/activitylist-service/activities/search/activities"


class GarminError(RuntimeError):
    """Missatge segur: mai inclou cos HTTP, headers, tokens ni URL amb query."""


@dataclass(repr=False)
class Token:
    value: str = field(repr=False)
    deadline: float


class GarminClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        approved: bool = False,
        contract_verified: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        min_interval: float = 1.0,
        max_retries: int = 3,
    ):
        if not approved or not contract_verified:
            raise GarminError("Connexió bloquejada: cal aprovació de secrets i contracte verificat")
        if not api_key or "\n" in api_key or "\r" in api_key:
            raise GarminError("Credencial no disponible o incompatible")
        if min_interval < 0 or max_retries < 0:
            raise ValueError("Configuració de reintents invàlida")
        self._api_key = api_key
        self._token: Token | None = None
        self.sleep, self.clock = sleep, clock
        self.wall_clock = wall_clock
        self.min_interval, self.max_retries = min_interval, max_retries
        self._last_request: float | None = None
        self._http = httpx.Client(
            base_url=BASE_URL, transport=transport, timeout=30, follow_redirects=False
        )

    def close(self) -> None:
        self._http.close()
        self._token = None
        self._api_key = ""

    def _request(
        self, method: str, path: str, *, max_bytes: int = 16 * 1024 * 1024, **kwargs: Any
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            if self._last_request is not None:
                self.sleep(max(0, self.min_interval - (self.clock() - self._last_request)))
            self._last_request = self.clock()
            try:
                with self._http.stream(method, path, **kwargs) as stream:
                    chunks = []
                    size = 0
                    for chunk in stream.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise GarminError("Resposta superior al límit de mida")
                        chunks.append(chunk)
                    response = httpx.Response(
                        stream.status_code,
                        headers=stream.headers,
                        content=b"".join(chunks),
                        request=stream.request,
                    )
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise GarminError("Error de transport; reintents exhaurits") from None
                self.sleep(min(60, 2**attempt + random.random()))
                continue
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == self.max_retries:
                    raise GarminError(f"HTTP {response.status_code}; reintents exhaurits")
                retry = response.headers.get("Retry-After", "")
                try:
                    delay = float(retry)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(retry) - datetime.now(UTC)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        delay = 2**attempt + random.random()
                if not math.isfinite(delay) or delay > 60:
                    raise GarminError("Retry-After llarg; reprendre la sincronització més tard")
                self.sleep(max(0, delay))
                continue
            return response
        raise GarminError("Reintents exhaurits")

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise GarminError("Resposta JSON invàlida") from None

    def _authenticate(self) -> None:
        response = self._request(
            "POST",
            TOKEN_PATH,
            headers={"Accept": "*/*", "Authorization": f"ApiKey {self._api_key}"},
        )
        if response.status_code != 200:
            raise GarminError(f"Autenticació rebutjada (HTTP {response.status_code})")
        # Referència oficial Garmin: JWT en text, sense embolcall OAuth JSON.
        token = response.text.strip()
        try:
            parts = token.split(".")
            if len(parts) != 3 or any(not part for part in parts):
                raise ValueError
            if any(
                c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                for part in parts
                for c in part
            ):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            expiry = payload["exp"]
            if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
                raise ValueError
            remaining = expiry - self.wall_clock()
            if not math.isfinite(remaining) or remaining <= 0:
                raise ValueError
        except (ValueError, KeyError, TypeError, OverflowError, binascii.Error):
            raise GarminError("Token JWT o caducitat exp no verificable") from None
        # exp només programa la memòria cau. No autentiquem ni validem signatures JWT;
        # el servidor Garmin verifica el token a través de TLS verificat.
        self._token = Token(token, self.clock() + min(remaining, 86400) * 0.9)

    def _get(
        self,
        path: str,
        params: dict | None = None,
        *,
        max_bytes: int = 16 * 1024 * 1024,
        accept: str = "application/json",
    ) -> httpx.Response:
        for attempt in range(2):
            if not self._token or self.clock() >= self._token.deadline:
                self._authenticate()
            response = self._request(
                "GET",
                path,
                params=params,
                max_bytes=max_bytes,
                headers={"Accept": accept, "Authorization": f"Bearer {self._token.value}"},
            )
            if response.status_code == 401 and attempt == 0:
                self._token = None
                continue
            if response.status_code != 200:
                raise GarminError(f"Petició rebutjada (HTTP {response.status_code})")
            return response
        raise GarminError("Autorització rebutjada després de renovar token")

    def search(self, offset: int, limit: int) -> list[dict]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Paginació invàlida")
        obj = self._json(self._get(SEARCH_PATH, {"start": offset, "limit": limit}))
        if not isinstance(obj, list) or not all(isinstance(x, dict) for x in obj):
            raise GarminError("Esquema de cerca desconegut")
        if len(obj) > limit:
            raise GarminError("Pàgina superior al límit sol·licitat")
        return obj

    @staticmethod
    def _id(activity_id: str) -> str:
        if (
            not str(activity_id).isascii()
            or not str(activity_id).isdecimal()
            or int(activity_id) <= 0
        ):
            raise ValueError("activityId invàlid")
        return str(activity_id)

    def detail(self, activity_id: str) -> dict:
        obj = self._json(self._get(f"/activity-service/activity/{self._id(activity_id)}"))
        if not isinstance(obj, dict):
            raise GarminError("Esquema de detall desconegut")
        return obj

    def download(self, activity_id: str) -> bytes:
        content = self._get(
            f"/download-service/files/activity/{self._id(activity_id)}",
            max_bytes=128 * 1024 * 1024,
            accept="application/zip, application/x-zip-compressed, application/octet-stream",
        ).content
        if not content:
            raise GarminError("Descàrrega buida")
        return content
