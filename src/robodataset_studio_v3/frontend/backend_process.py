from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from robodataset_studio_v3.frontend.api_client import ApiClient


class BackendProcess:
    def __init__(self, api: ApiClient, root_dir: Path | None = None) -> None:
        self.api = api
        self.root_dir = root_dir or Path(__file__).resolve().parents[3]
        self.process: subprocess.Popen[str] | None = None
        self.host = "127.0.0.1"
        self.port = self._port_from_url(api.base_url) or 8765

    def ensure_running(self, timeout_sec: float = 8.0) -> None:
        if self.is_healthy():
            return
        self.port = self._find_available_port(self.port)
        self.api.base_url = f"http://{self.host}:{self.port}"
        self.start()
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self.is_healthy():
                return
            time.sleep(0.15)
        raise RuntimeError("FastAPI backend did not become healthy before timeout")

    def is_healthy(self) -> bool:
        try:
            data = self.api.health()
        except Exception:
            return False
        return data.get("status") == "ok"

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        env = os.environ.copy()
        src = str(self.root_dir / "src")
        env["PYTHONPATH"] = f"{src}:{env.get('PYTHONPATH', '')}" if env.get("PYTHONPATH") else src
        env["ROBODATASET_V3_BACKEND_HOST"] = self.host
        env["ROBODATASET_V3_BACKEND_PORT"] = str(self.port)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "robodataset_studio_v3.backend.main"],
            cwd=str(self.root_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def _find_available_port(self, preferred: int) -> int:
        for port in [preferred, *range(8766, 8790)]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.1)
                if sock.connect_ex((self.host, port)) != 0:
                    return port
        raise RuntimeError("no available local backend port found")

    def _port_from_url(self, url: str) -> int | None:
        try:
            return int(url.rstrip("/").rsplit(":", 1)[1])
        except Exception:
            return None

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3.0)
