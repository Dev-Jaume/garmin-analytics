import json
import os
import sys

import pytest

from garmin_running.cli import main


def test_offline_workflow_without_secrets(tmp_path, monkeypatch, capsys, fit_bytes):
    monkeypatch.setattr(os, "environ", {})
    directory = tmp_path / "private"
    base = ["gra", "--data-dir", str(directory)]
    monkeypatch.setattr(sys, "argv", base + ["init"])
    assert main() == 0
    capsys.readouterr()
    path = tmp_path / "synthetic.fit"
    path.write_bytes(fit_bytes)
    monkeypatch.setattr(sys, "argv", base + ["import", str(path)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["imported"] == 1
    monkeypatch.setattr(sys, "argv", base + ["coverage"])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["activities"] == 1
    assert report["status"] == "Cobertura no verificada"


def test_sync_blocked_before_secret_read(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gra", "--data-dir", str(tmp_path / "not-created"), "sync"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not (tmp_path / "not-created").exists()
