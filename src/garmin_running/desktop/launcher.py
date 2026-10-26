"""Inici local: loopback imposat, telemetria desactivada i navegador automàtic."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from filelock import FileLock, Timeout

from garmin_running.desktop.local import LocalPaths, atomic_json


def streamlit_command(port=8501):
    if not 1024 <= port <= 65535:
        raise ValueError("Port invàlid")
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).with_name("app.py")),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.enableCORS=true",
        "--server.enableXsrfProtection=true",
        "--server.fileWatcherType=none",
    ]


def main():
    parser = argparse.ArgumentParser(description="Garmin Running Analytics local")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()
    if args.data_dir:
        os.environ["GRA_DATA_DIR"] = str(args.data_dir.resolve())
    paths = LocalPaths.discover().ensure()
    command = streamlit_command(args.port)
    if args.diagnose:
        print(
            json.dumps(
                {
                    "address": "127.0.0.1",
                    "data_dir": str(paths.root),
                    "credential_source": "Windows Credential Manager",
                    "command": command,
                }
            )
        )
        return 0
    lock = FileLock(str(paths.root / "app.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        try:
            state = json.loads((paths.root / "server.json").read_text())
            port = int(state["port"])
            if 1024 <= port <= 65535:
                webbrowser.open(f"http://127.0.0.1:{port}")
        except (OSError, ValueError, KeyError):
            print("L'aplicació ja s'està iniciant.")
        return 0
    process = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", args.port))
            except OSError:
                raise RuntimeError(
                    "Port local ocupat; tanca l'altra aplicació o tria un altre port"
                ) from None
        atomic_json(paths.root / "server.json", {"port": args.port})
        # Sense HTTP_PROXY per a loopback; això no modifica el proxy de Garmin.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        process = subprocess.Popen(command)
        url = f"http://127.0.0.1:{args.port}"
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("El servidor local no s'ha pogut iniciar; reviseu el port")
            try:
                with opener.open(url + "/_stcore/health", timeout=0.5) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            raise RuntimeError("El servidor local ha excedit el temps d'inici")
        print("Garmin Running Analytics en execució local. Tanqueu aquesta finestra per sortir.")
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
