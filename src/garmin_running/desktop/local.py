"""Rutes locals, preferències sense secrets i logging amb missatges controlats."""

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path, PureWindowsPath

from sqlalchemy.engine import URL

APP_NAME = "GarminRunningAnalytics"


def windows_data_path(local_appdata: str, override: str | None = None) -> PureWindowsPath:
    path = PureWindowsPath(override) if override else PureWindowsPath(local_appdata) / APP_NAME
    if path.drive.startswith("\\\\"):
        raise ValueError("Cal un disc local, no una ruta de xarxa UNC")
    if not path.is_absolute():
        raise ValueError("La ruta de dades ha de ser absoluta")
    return path


@dataclass(frozen=True)
class LocalPaths:
    root: Path

    @classmethod
    def discover(cls):
        custom = os.environ.get("GRA_DATA_DIR")
        if custom:
            root = (
                Path(windows_data_path(custom, custom)) if sys.platform == "win32" else Path(custom)
            )
        elif sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA")
            if not base:
                raise RuntimeError("LOCALAPPDATA no disponible")
            root = Path(windows_data_path(base))
        else:
            # Entorn de desenvolupament; Windows és el destí de distribució.
            root = Path.cwd() / "private" / "desktop"
        if not root.is_absolute():
            root = root.resolve()
        return cls(root)

    def ensure(self):
        for folder in ("", "originals", "imports", "staging", "backups", "logs"):
            (self.root / folder).mkdir(parents=True, exist_ok=True, mode=0o700)
        return self

    @property
    def database_url(self):
        return URL.create("sqlite", database=str(self.root / "analytics.sqlite3"))


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Preferences:
    def __init__(self, paths: LocalPaths):
        self.path = paths.root / "settings.json"

    def load(self):
        defaults = {
            "consent": False,
            "auto_sync": False,
            "credential_configured": False,
            "thresholds": [],
            "races": [],
            "max_gap_seconds": 10,
        }
        self.error = False
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("Preferències invàlides")
                defaults.update({key: value[key] for key in defaults if key in value})
                for key in ("consent", "auto_sync", "credential_configured"):
                    defaults[key] = defaults[key] is True
            except (OSError, ValueError):
                self.error = True
        return defaults

    def save(self, values: dict):
        allowed = self.load()
        if set(values) - set(allowed):
            raise ValueError("Preferència no admesa; mai guardar secrets en JSON")
        allowed.update(values)
        atomic_json(self.path, allowed)


def event_logger(paths: LocalPaths):
    logger = logging.getLogger(f"gra.local.{paths.root}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            paths.root / "logs" / "events.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
