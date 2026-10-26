"""Representació normalitzada; l'original immutable sempre es conserva."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

ALGORITHM_VERSION = "ingestion-1"


class DataError(ValueError):
    """Dades no compatibles o amb integritat insuficient."""


def instant(value: Any) -> str | None:
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    # FIT i camps Garmin explícitament GMT són UTC encara que no portin offset.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


@dataclass
class ActivityData:
    start: str | None
    sport: str
    metrics: dict[str, Any] = field(default_factory=dict)
    samples: list[dict[str, Any]] = field(default_factory=list)
    laps: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    timezone: str | None = None
    device: str | None = None
    identity: str | None = None

    @property
    def is_running(self) -> bool:
        return self.sport in {"running", "trail_running", "treadmill_running", "track_running"}
