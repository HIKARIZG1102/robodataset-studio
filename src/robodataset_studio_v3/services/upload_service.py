from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from threading import Thread
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

    def manifest(self, local_path: str) -> dict[str, Any]:
        local = Path(local_path).expanduser()
        manifest = UploadManifest().build(local)
        preview_files = manifest.get("files", [])[:200]
        result = {
            "local_path": str(local),
            "schema": manifest.get("schema", ""),
            "source": manifest.get("source", ""),
            "source_type": manifest.get("source_type", ""),
            "file_count": manifest.get("file_count", 0),
            "total_size_bytes": manifest.get("total_size_bytes", 0),
            "preview_files": preview_files,
            "truncated": len(preview_files) < int(manifest.get("file_count", 0) or 0),
        }
        task = task_service.run_instant("upload_manifest", f"built upload manifest for {local}", result)
        return {"task_id": task.task_id, "result": result}

    def verify_local_manifest(self, local_path: str) -> dict[str, Any]:
        local = Path(local_path).expanduser()
        manifest = UploadManifest().build(local)
        missing = []
        mismatched = []
        checked = 0
        base = Path(str(manifest.get("root") or local))
        for entry in manifest.get("files", []):
            rel = str(entry.get("path", ""))
            path = base / rel
            if not path.exists():
                missing.append(rel)
                continue
            checked += 1
            if path.stat().st_size != int(entry.get("size_bytes", -1)):
                mismatched.append(rel)
        result = {
            "local_path": str(local),
            "ok": not missing and not mismatched,
            "checked": checked,
            "missing": missing,
            "mismatched": mismatched,
            "file_count": manifest.get("file_count", 0),
            "total_size_bytes": manifest.get("total_size_bytes", 0),
        }
        task = task_service.run_instant("upload_manifest_verify", f"verified local manifest for {local}", result)
        return {"task_id": task.task_id, "result": result}

    def remote_list(self, host: str, username: str, remote_path: str, port: int = 22) -> dict[str, Any]:
        user_host = self._user_host(host, username)
        script = self._remote_list_script(remote_path or "/")
        completed = subprocess.run(self._ssh_command(user_host, port, "python3", "-"), input=script, text=True, capture_output=True, check=False, timeout=20)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote list failed")
        payload = json.loads(completed.stdout[completed.stdout.find("{") : completed.stdout.rfind("}") + 1])
        task = task_service.run_instant("upload_remote_list", f"listed remote {user_host}:{remote_path}", payload)
        return {"task_id": task.task_id, "result": payload}

    def remote_mkdir(self, host: str, username: str, remote_path: str, folder_name: str, port: int = 22) -> dict[str, Any]:
        clean = "".join(ch for ch in folder_name.strip() if ch.isalnum() or ch in {"_", "-", "."})
        if not clean:
            raise ValueError("folder name is empty")
        new_path = str(PurePosixPath(remote_path or "/") / clean)
        user_host = self._user_host(host, username)
        script = "from pathlib import Path\nimport sys\nPath(sys.argv[1]).mkdir(parents=True, exist_ok=True)\nprint(sys.argv[1])\n"
        completed = subprocess.run(self._ssh_command(user_host, port, "python3", "-", new_path), input=script, text=True, capture_output=True, check=False, timeout=20)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote mkdir failed")
        result = {"ok": True, "path": new_path, "host": user_host}
        task = task_service.run_instant("upload_remote_mkdir", f"created remote folder {new_path}", result)
        return {"task_id": task.task_id, "result": result}

    def remote_space(self, host: str, username: str, remote_path: str, port: int = 22) -> dict[str, Any]:
        user_host = self._user_host(host, username)
        script = (
            "import json, os, sys\n"
            "path=sys.argv[1]\n"
            "stat=os.statvfs(path)\n"
            "print(json.dumps({'path': path, 'total_bytes': stat.f_frsize*stat.f_blocks, 'free_bytes': stat.f_frsize*stat.f_bfree, 'available_bytes': stat.f_frsize*stat.f_bavail}))\n"
        )
        completed = subprocess.run(self._ssh_command(user_host, port, "python3", "-", remote_path or "/"), input=script, text=True, capture_output=True, check=False, timeout=20)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote space check failed")
        payload = json.loads(completed.stdout[completed.stdout.find("{") : completed.stdout.rfind("}") + 1])
        task = task_service.run_instant("upload_remote_space", f"checked remote space {user_host}:{remote_path}", payload)
        return {"task_id": task.task_id, "result": payload}

    def start(self, local_path: str, remote_path: str, host: str = "", username: str = "", repair: bool = False, port: int = 22) -> dict[str, Any]:
        task = task_service.create_task("upload_repair" if repair else "upload", "upload started")
        Thread(target=self._start_worker, args=(task.task_id, local_path, remote_path, host, username, repair, port), daemon=True).start()
        return {"task_id": task.task_id, "local_path": local_path, "remote_path": remote_path, "host": host, "username": username, "repair": repair, "port": port}

    def _start_worker(self, task_id: str, local_path: str, remote_path: str, host: str, username: str, repair: bool, port: int) -> None:
        result = self._start_sync(local_path, remote_path, host, username, repair, port)
        if result.get("ok"):
            task_service.complete_task(task_id, message="upload finished", result=result)
        else:
            task_service.fail_task(task_id, message="upload failed", error=str(result.get("error", "")))

    def _start_sync(self, local_path: str, remote_path: str, host: str = "", username: str = "", repair: bool = False, port: int = 22) -> dict[str, Any]:
        local = Path(local_path).expanduser()
        deps = self.dependency_check()
        result = {
            "local_path": str(local),
            "remote_path": remote_path,
            "host": host,
            "username": username,
            "repair": repair,
            "port": port,
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
                    verify_result = self._remote_verify(local, target, port)
                    rel_paths = self._repair_paths(verify_result)
                    if not rel_paths:
                        result.update({"ok": True, "message": "remote already verified", "verify": verify_result})
                    else:
                        command = self._repair_command(local, target, rel_paths, port)
                        result.update(self._run_command(command))
                        result["verify"] = verify_result
                else:
                    command = self._rsync_command(local, target, port)
                    result.update(self._run_command(command))
            except Exception as exc:
                result["ok"] = False
                result["error"] = str(exc)
        return result

    def verify(self, local_path: str, remote_path: str, host: str = "", port: int = 22) -> dict[str, Any]:
        task = task_service.create_task("upload_verify", "remote verification started")
        Thread(target=self._verify_worker, args=(task.task_id, local_path, remote_path, host, port), daemon=True).start()
        return {"task_id": task.task_id, "local_path": local_path, "remote_path": remote_path, "host": host, "port": port}

    def _verify_worker(self, task_id: str, local_path: str, remote_path: str, host: str, port: int) -> None:
        local = Path(local_path).expanduser()
        try:
            result = self._remote_verify(local, self._target(host, "", remote_path), port)
            task_service.complete_task(task_id, message="remote verification finished", result=result)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "local_path": str(local), "remote_path": remote_path, "host": host}
            task_service.fail_task(task_id, message="remote verification failed", error=str(exc))

    def _target(self, host: str, username: str, remote_path: str) -> str:
        user_host = self._user_host(host, username)
        if not user_host or not remote_path:
            raise ValueError("host and remote_path are required")
        return f"{user_host}:{remote_path.rstrip('/')}"

    def _user_host(self, host: str, username: str = "") -> str:
        if "@" in host:
            return host
        if username:
            return f"{username}@{host}"
        return host

    def _ssh_command(self, user_host: str, port: int, *remote_command: str) -> list[str]:
        command = ["ssh"]
        if int(port or 22) != 22:
            command.extend(["-p", str(int(port))])
        command.append(user_host)
        command.extend(remote_command)
        return command

    def _remote_list_script(self, remote_path: str) -> str:
        return f"""\
import json
from pathlib import Path
root = Path({remote_path!r}).expanduser()
entries = []
for item in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
    try:
        stat = item.stat()
        entries.append({{"name": item.name, "is_dir": item.is_dir(), "size": stat.st_size, "path": str(item)}})
    except OSError:
        entries.append({{"name": item.name, "is_dir": item.is_dir(), "size": -1, "path": str(item)}})
print(json.dumps({{"ok": True, "path": str(root), "entries": entries}}, ensure_ascii=False))
"""

    def _rsync_command(self, local_path: Path, target: str, port: int = 22) -> list[str]:
        source = str(local_path)
        if local_path.is_dir():
            source = f"{source.rstrip('/')}/"
        command = ["rsync", "-avh", "--progress", "--partial", "--partial-dir=.rsync-partial", "--append-verify"]
        if int(port or 22) != 22:
            command.extend(["-e", f"ssh -p {int(port)}"])
        command.extend([source, target])
        return command

    def _repair_command(self, local_path: Path, target: str, rel_paths: list[str], port: int = 22) -> list[str]:
        source_root = local_path.parent if local_path.is_file() else local_path
        files_from = self._write_files_from(rel_paths)
        command = [
            "rsync",
            "-avh",
            "--progress",
            "--partial",
            "--partial-dir=.rsync-partial",
            "--append-verify",
        ]
        if int(port or 22) != 22:
            command.extend(["-e", f"ssh -p {int(port)}"])
        command.extend(
            [
            "--files-from",
            str(files_from),
            f"{str(source_root).rstrip('/')}/",
            target,
            ]
        )
        return command

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

    def _remote_verify(self, local_path: Path, target: str, port: int = 22) -> dict[str, Any]:
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
        ssh_command = ["ssh"]
        if int(port or 22) != 22:
            ssh_command.extend(["-p", str(int(port))])
        ssh_command.extend([user_host, "python3", "-"])
        completed = subprocess.run(ssh_command, input=script, text=True, capture_output=True, check=False)
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
