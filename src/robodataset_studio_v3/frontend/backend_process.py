from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import tempfile
import signal
from pathlib import Path

from robodataset_studio_v3.frontend.api_client import ApiClient
from robodataset_studio_v3.core.runtime_env import apply_ros_environment, default_ros_setup


class BackendProcess:
    def __init__(self, api: ApiClient, root_dir: Path | None = None) -> None:
        self.api = api
        self.root_dir = root_dir or Path(__file__).resolve().parents[3]
        self.process: subprocess.Popen[str] | None = None
        self.host = "127.0.0.1"
        self.port = self._port_from_url(api.base_url) or 8765
        self.log_path: Path | None = None

    def ensure_running(self, timeout_sec: float = 8.0) -> None:
        self.cleanup_stale_backends()
        reusable_port = self._find_compatible_backend_port(self.port)
        if reusable_port is not None:
            self.port = reusable_port
            self.api.base_url = f"http://{self.host}:{self.port}"
            return
        self.port = self._find_free_port(self.port)
        self.api.base_url = f"http://{self.host}:{self.port}"
        self.start()
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self.is_healthy() and self.has_required_routes():
                return
            if self.process is not None and self.process.poll() is not None:
                break
            time.sleep(0.15)
        raise RuntimeError(self._startup_error())

    def is_healthy(self) -> bool:
        try:
            data = self.api.health()
        except Exception:
            return False
        return self._health_compatible(data)

    def has_required_routes(self) -> bool:
        try:
            configs = self.api.get("/api/config/library", timeout=2.0)
        except Exception:
            return False
        return isinstance(configs, list)

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        env = os.environ.copy()
        src = str(self.root_dir / "src")
        env["PYTHONPATH"] = f"{src}:{env.get('PYTHONPATH', '')}" if env.get("PYTHONPATH") else src
        env["ROBODATASET_V3_BACKEND_HOST"] = self.host
        env["ROBODATASET_V3_BACKEND_PORT"] = str(self.port)
        env["ROBODATASET_V3_ROOT"] = str(self.root_dir)
        env.setdefault("ROS_SETUP", default_ros_setup())
        apply_ros_environment(env)
        log_dir = Path(tempfile.gettempdir())
        self.log_path = log_dir / f"robodataset_studio_v3_backend_{self.port}.log"
        log_file = self.log_path.open("w", encoding="utf-8")
        python = self._python_executable()
        self.process = subprocess.Popen(
            [python, "-m", "robodataset_studio_v3.backend.main"],
            cwd=str(self.root_dir),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

    def cleanup_stale_backends(self) -> None:
        marker = "robodataset_studio_v3.backend.main"
        root_marker = str(self.root_dir)
        try:
            output = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
        except Exception:
            return
        current_pid = os.getpid()
        for line in output.splitlines():
            line = line.strip()
            if marker not in line:
                continue
            try:
                pid_text = line.split(None, 1)[0]
                pid = int(pid_text)
            except Exception:
                continue
            if pid == current_pid:
                continue
            if not self._pid_cwd_matches(pid, root_marker):
                continue
            self._kill_pid(pid)

    def _pid_cwd_matches(self, pid: int, root_marker: str) -> bool:
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except Exception:
            return False
        return cwd == root_marker

    def _python_executable(self) -> str:
        image_venv = os.environ.get("ROBODATASET_VENV", "")
        if os.environ.get("ROBODATASET_DOCKER") and image_venv:
            image_python = Path(image_venv) / "bin" / "python"
            if image_python.exists():
                return str(image_python)
        venv_python = self.root_dir / ".venv" / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        return sys.executable

    def _find_compatible_backend_port(self, preferred: int) -> int | None:
        original_base_url = self.api.base_url
        for port in [preferred, *range(8766, 8790)]:
            if not self._port_in_use(port):
                continue
            self.api.base_url = f"http://{self.host}:{port}"
            try:
                if self.is_healthy() and self.has_required_routes():
                    return port
            finally:
                self.api.base_url = original_base_url
        return None

    def _find_free_port(self, preferred: int) -> int:
        for port in [preferred, *range(8766, 8790)]:
            if not self._port_in_use(port):
                return port
        raise RuntimeError("no available local backend port found")

    def _port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            return sock.connect_ex((self.host, port)) == 0

    def _health_compatible(self, data: dict) -> bool:
        if data.get("status") != "ok" or data.get("service") != "robodataset-studio-v3":
            return False
        if "docker" not in data or "root" not in data:
            return False
        expected_docker = self._docker_mode()
        remote_docker = bool(data.get("docker"))
        if remote_docker != expected_docker:
            return False
        remote_root = str(data.get("root") or "")
        if remote_root:
            try:
                return Path(remote_root).resolve() == self.root_dir.resolve()
            except Exception:
                return remote_root == str(self.root_dir)
        return not remote_docker

    def _docker_mode(self) -> bool:
        return str(os.environ.get("ROBODATASET_DOCKER", "")).lower() in {"1", "true", "yes"}

    def _port_from_url(self, url: str) -> int | None:
        try:
            return int(url.rstrip("/").rsplit(":", 1)[1])
        except Exception:
            return None

    def _startup_error(self) -> str:
        parts = ["FastAPI backend did not become healthy before timeout."]
        if self.process is not None:
            code = self.process.poll()
            if code is not None:
                parts.append(f"Backend process exited with code {code}.")
        if self.log_path is not None:
            parts.append(f"Log: {self.log_path}")
            try:
                lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = "\n".join(lines[-40:])
                if tail:
                    parts.append("Backend log tail:\n" + tail)
            except Exception as exc:
                parts.append(f"Could not read backend log: {exc}")
        return "\n".join(parts)

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        pid = self.process.pid
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            self.process.terminate()
        try:
            self.process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                self.process.kill()
            self.process.wait(timeout=1.5)
        finally:
            self.process = None

    def _kill_pid(self, pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                return
        deadline = time.time() + 1.0
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        try:
            os.killpg(pid, signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
