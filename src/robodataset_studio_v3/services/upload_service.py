from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from robodataset_studio_v3.upload.manifest import UploadManifest
from robodataset_studio_v3.services.task_service import task_service


class UploadService:
    def dependency_check(self) -> dict[str, Any]:
        result = {
            "ssh": shutil.which("ssh") is not None,
            "rsync": shutil.which("rsync") is not None,
            "scp": shutil.which("scp") is not None,
        }
        result["ok"] = result["ssh"] and (result["rsync"] or result["scp"])
        return result

    def connect(self, host: str, username: str = "", port: int = 22) -> dict[str, Any]:
        deps = self.dependency_check()
        result = {"host": host, "username": username, "port": port, "dependencies": deps}
        if not host:
            result["ok"] = False
            result["error"] = "host is empty"
        else:
            result["ok"] = deps["ssh"]
            result["message"] = "connection parameters accepted; remote login test is deferred to upload/remote browse"
        task = task_service.run_instant("upload_connect", f"checked upload profile {host}", result)
        return {"task_id": task.task_id, "result": result}

    def start(self, local_path: str, remote_path: str, host: str = "", username: str = "", repair: bool = False) -> dict[str, Any]:
        local = Path(local_path).expanduser()
        deps = self.dependency_check()
        task = task_service.create_task("upload_repair" if repair else "upload", "upload started")
        result = {
            "local_path": str(local),
            "remote_path": remote_path,
            "host": host,
            "username": username,
            "repair": repair,
            "dependencies": deps,
            "local_exists": local.exists(),
        }
        if not local.exists():
            result["ok"] = False
            result["error"] = "local path does not exist"
        elif not host:
            result["ok"] = False
            result["error"] = "host is empty"
        elif repair and not deps["rsync"]:
            result["ok"] = False
            result["error"] = "repair/resume requires rsync"
        else:
            target = self._target(host, username, remote_path)
            try:
                if repair:
                    verify_result = self._remote_verify(local, target)
                    rel_paths = self._repair_paths(verify_result)
                    if not rel_paths:
                        result.update({"ok": True, "message": "remote already verified", "verify": verify_result})
                    else:
                        command = self._repair_command(local, target, rel_paths)
                        result.update(self._run_command(command))
                        result["verify"] = verify_result
                else:
                    command = self._rsync_command(local, target)
                    result.update(self._run_command(command))
            except Exception as exc:
                result["ok"] = False
                result["error"] = str(exc)
        if result.get("ok"):
            task_service.complete_task(task.task_id, message="upload finished", result=result)
        else:
            task_service.fail_task(task.task_id, message="upload failed", error=str(result.get("error", "")))
        return {"task_id": task.task_id, "result": result}

    def verify(self, local_path: str, remote_path: str, host: str = "") -> dict[str, Any]:
        local = Path(local_path).expanduser()
        task = task_service.create_task("upload_verify", "remote verification started")
        try:
            result = self._remote_verify(local, self._target(host, "", remote_path))
            task_service.complete_task(task.task_id, message="remote verification finished", result=result)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "local_path": str(local), "remote_path": remote_path, "host": host}
            task_service.fail_task(task.task_id, message="remote verification failed", error=str(exc))
        return {"task_id": task.task_id, "result": result}

    def _target(self, host: str, username: str, remote_path: str) -> str:
        if "@" in host:
            user_host = host
        elif username:
            user_host = f"{username}@{host}"
        else:
            user_host = host
        if not user_host or not remote_path:
            raise ValueError("host and remote_path are required")
        return f"{user_host}:{remote_path.rstrip('/')}"

    def _rsync_command(self, local_path: Path, target: str) -> list[str]:
        source = str(local_path)
        if local_path.is_dir():
            source = f"{source.rstrip('/')}/"
        return ["rsync", "-avh", "--progress", "--partial", "--partial-dir=.rsync-partial", "--append-verify", source, target]

    def _repair_command(self, local_path: Path, target: str, rel_paths: list[str]) -> list[str]:
        source_root = local_path.parent if local_path.is_file() else local_path
        files_from = self._write_files_from(rel_paths)
        return [
            "rsync",
            "-avh",
            "--progress",
            "--partial",
            "--partial-dir=.rsync-partial",
            "--append-verify",
            "--files-from",
            str(files_from),
            f"{str(source_root).rstrip('/')}/",
            target,
        ]

    def _run_command(self, command: list[str]) -> dict[str, Any]:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout.splitlines()[-80:],
            "stderr_tail": completed.stderr.splitlines()[-80:],
            "error": "" if completed.returncode == 0 else completed.stderr.strip(),
        }

    def _remote_verify(self, local_path: Path, target: str) -> dict[str, Any]:
        user_host, remote_root = target.split(":", 1)
        manifest = UploadManifest().build(local_path)
        checks = []
        for entry in manifest.get("files", []):
            rel_path = str(entry.get("path", ""))
            checks.append(
                {
                    "path": rel_path,
                    "remote": str(PurePosixPath(remote_root.rstrip("/")) / PurePosixPath(rel_path)),
                    "sha256": str(entry.get("sha256", "")),
                    "size_bytes": int(entry.get("size_bytes", -1)),
                }
            )
        script = self._remote_verify_script(checks)
        completed = subprocess.run(["ssh", user_host, "python3", "-"], input=script, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote verification failed")
        payload = json.loads(completed.stdout[completed.stdout.find("{") : completed.stdout.rfind("}") + 1])
        payload["file_count"] = manifest.get("file_count", 0)
        return payload

    def _remote_verify_script(self, checks: list[dict[str, Any]]) -> str:
        payload = json.dumps(checks, ensure_ascii=False)
        return f"""\
import hashlib
import json
from pathlib import Path
checks = json.loads({payload!r})
missing = []
mismatched = []
checked = 0
for entry in checks:
    path = Path(entry["remote"])
    if not path.exists():
        missing.append(entry["path"])
        continue
    checked += 1
    size_ok = path.stat().st_size == int(entry["size_bytes"])
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if not size_ok or digest.hexdigest() != entry["sha256"]:
        mismatched.append(entry["path"])
print(json.dumps({{"ok": not missing and not mismatched, "checked": checked, "missing": missing, "mismatched": mismatched}}, ensure_ascii=False))
"""

    def _repair_paths(self, verify_result: dict[str, Any]) -> list[str]:
        paths = []
        for key in ("missing", "mismatched"):
            value = verify_result.get(key, [])
            if isinstance(value, list):
                paths.extend(str(item) for item in value)
        return sorted(set(path for path in paths if path and not path.startswith("/") and ".." not in PurePosixPath(path).parts))

    def _write_files_from(self, rel_paths: list[str]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="robodataset_v3_rsync_", suffix=".txt", delete=False)
        with handle:
            for rel_path in rel_paths:
                handle.write(f"{rel_path}\n")
        return Path(handle.name)


upload_service = UploadService()
