"""Flux de verificació amb un FIT sintètic, sense dades reals ni credencials."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from conftest import synthetic_fit  # noqa: E402

folder = ROOT / "work" / "smoke"
folder.mkdir(parents=True, exist_ok=True)
fit_path = folder / "synthetic.fit"
fit_path.write_bytes(synthetic_fit())
base = [sys.executable, "-m", "garmin_running.cli", "--data-dir", str(folder / "private")]
for command in [["init"], ["import", str(fit_path)], ["import", str(fit_path)], ["coverage"]]:
    result = subprocess.run(base + command, check=True, capture_output=True, text=True)
    if command[0] == "coverage":
        report = json.loads(result.stdout)
        assert report["activities"] == 1
        assert report["status"] == "Cobertura no verificada"
        print(
            json.dumps(
                {
                    "synthetic": True,
                    "unique_activities": report["activities"],
                    "coverage": report["status"],
                    "repeat_import": "idempotent",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
