from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
import stat
import hashlib
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from threading import Thread
from typing import Any

from robodataset_studio_v3.upload.manifest import UploadManifest
from robodataset_studio_v3.services.task_service import task_service


@dataclass
class SshConnection:
    host: str
    port: int
    username: str
    remote_path: str
    password: str = ""
    key_path: str = ""

    @property
    def user_host(self) -> str:
        if "@" in self.host:
            return self.host
        return f"{self.username}@{self.host}" if self.username else self.host

    @property
    def target(self) -> str:
        return f"{self.user_host}:{self.remote_path.rstrip('/')}"

    @property
    def auth_mode(self) -> str:
        if self.key_path:
            return "key"
        if self.password:
            return "password"
        return "agent_or_default_key"


class UploadService:
    def dependency_check(self) -> dict[str, Any]:
        result = {
            "ssh": shutil.which("ssh") is not None,
            "rsync": shutil.which("rsync") is not None,
            "scp": shutil.which("scp") is not None,
            "paramiko": self._paramiko_available(),
        }
        result["ok"] = (result["ssh"] and (result["rsync"] or result["scp"])) or result["paramiko"]
        return result

    def connect(self, host: str, username: str = "", port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        deps = self.dependency_check()
        connection = self._connection(host, username, "/", port, password, key_path)
        result = {"host": host, "username": username, "port": port, "auth_mode": connection.auth_mode, "dependencies": deps}
        if not host:
            result["ok"] = False
            result["error"] = "host is empty"
        else:
            result["ok"] = deps["paramiko"] if (password or key_path) else deps["ssh"]
            result["message"] = "connection parameters accepted; remote login test runs when listing the remote directory"
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

    def remote_list(self, host: str, username: str, remote_path: str, port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        connection = self._connection(host, username, remote_path, port, password, key_path)
        if connection.password or connection.key_path:
            payload = self._remote_list_paramiko(connection)
        else:
            script = self._remote_list_script(connection.remote_path)
            completed = subprocess.run(self._ssh_command(connection.user_host, connection.port, "python3", "-"), input=script, text=True, capture_output=True, check=False, timeout=20)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote list failed")
            payload = json.loads(completed.stdout[completed.stdout.find("{") : completed.stdout.rfind("}") + 1])
        task = task_service.run_instant("upload_remote_list", f"listed remote {connection.user_host}:{connection.remote_path}", payload)
        return {"task_id": task.task_id, "result": payload}

    def remote_mkdir(self, host: str, username: str, remote_path: str, folder_name: str, port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        clean = "".join(ch for ch in folder_name.strip() if ch.isalnum() or ch in {"_", "-", "."})
        if not clean:
            raise ValueError("folder name is empty")
        new_path = str(PurePosixPath(remote_path or "/") / clean)
        connection = self._connection(host, username, remote_path, port, password, key_path)
        if connection.password or connection.key_path:
            self._mkdir_paramiko(connection, new_path)
        else:
            script = "from pathlib import Path\nimport sys\nPath(sys.argv[1]).mkdir(parents=True, exist_ok=True)\nprint(sys.argv[1])\n"
            completed = subprocess.run(self._ssh_command(connection.user_host, connection.port, "python3", "-", new_path), input=script, text=True, capture_output=True, check=False, timeout=20)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote mkdir failed")
        result = {"ok": True, "path": new_path, "host": connection.user_host}
        task = task_service.run_instant("upload_remote_mkdir", f"created remote folder {new_path}", result)
        return {"task_id": task.task_id, "result": result}

    def remote_space(self, host: str, username: str, remote_path: str, port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        connection = self._connection(host, username, remote_path, port, password, key_path)
        if connection.password or connection.key_path:
            payload = self._remote_space_paramiko(connection)
        else:
            script = (
                "import json, os, sys\n"
                "path=sys.argv[1]\n"
                "stat=os.statvfs(path)\n"
                "print(json.dumps({'path': path, 'total_bytes': stat.f_frsize*stat.f_blocks, 'free_bytes': stat.f_frsize*stat.f_bfree, 'available_bytes': stat.f_frsize*stat.f_bavail}))\n"
            )
            completed = subprocess.run(self._ssh_command(connection.user_host, connection.port, "python3", "-", connection.remote_path), input=script, text=True, capture_output=True, check=False, timeout=20)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "remote space check failed")
            payload = json.loads(completed.stdout[completed.stdout.find("{") : completed.stdout.rfind("}") + 1])
        task = task_service.run_instant("upload_remote_space", f"checked remote space {connection.user_host}:{connection.remote_path}", payload)
        return {"task_id": task.task_id, "result": payload}

    def start(self, local_path: str, remote_path: str, host: str = "", username: str = "", repair: bool = False, port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        task = task_service.create_task("upload_repair" if repair else "upload", "upload started")
        Thread(target=self._start_worker, args=(task.task_id, local_path, remote_path, host, username, repair, port, password, key_path), daemon=True).start()
        return {"task_id": task.task_id, "local_path": local_path, "remote_path": remote_path, "host": host, "username": username, "repair": repair, "port": port, "auth_mode": self._connection(host, username, remote_path, port, password, key_path).auth_mode}

    def _start_worker(self, task_id: str, local_path: str, remote_path: str, host: str, username: str, repair: bool, port: int, password: str, key_path: str) -> None:
        result = self._start_sync(local_path, remote_path, host, username, repair, port, password, key_path)
        if result.get("ok"):
            task_service.complete_task(task_id, message="upload finished", result=result)
        else:
            task_service.fail_task(task_id, message="upload failed", error=str(result.get("error", "")))

    def _start_sync(self, local_path: str, remote_path: str, host: str = "", username: str = "", repair: bool = False, port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        local = Path(local_path).expanduser()
        deps = self.dependency_check()
        connection = self._connection(host, username, remote_path, port, password, key_path)
        result = {
            "local_path": str(local),
            "remote_path": remote_path,
            "host": host,
            "username": username,
            "repair": repair,
            "port": port,
            "auth_mode": connection.auth_mode,
            "dependencies": deps,
            "local_exists": local.exists(),
        }
        if not local.exists():
            result["ok"] = False
            result["error"] = "local path does not exist"
        elif not host:
            result["ok"] = False
            result["error"] = "host is empty"
        elif (connection.password or connection.key_path) and not deps["paramiko"]:
            result["ok"] = False
            result["error"] = "password/key upload requires paramiko"
        elif repair and not (deps["rsync"] or connection.password or connection.key_path):
            result["ok"] = False
            result["error"] = "repair/resume requires rsync"
        else:
            try:
                if repair:
                    verify_result = self._remote_verify_connection(local, connection)
                    rel_paths = self._repair_paths(verify_result)
                    if not rel_paths:
                        result.update({"ok": True, "message": "remote already verified", "verify": verify_result})
                    elif connection.password or connection.key_path:
                        upload_result = self._upload_sftp(local, connection, rel_paths)
                        result.update({"ok": True, "verify": verify_result, **upload_result})
                    else:
                        command = self._repair_command(local, connection.target, rel_paths, connection.port, connection.key_path)
                        result.update(self._run_command(command))
                        result["verify"] = verify_result
                elif connection.password or connection.key_path:
                    result.update({"ok": True, **self._upload_sftp(local, connection)})
                else:
                    command = self._rsync_command(local, connection.target, connection.port, connection.key_path)
                    result.update(self._run_command(command))
            except Exception as exc:
                result["ok"] = False
                result["error"] = str(exc)
        return result

    def verify(self, local_path: str, remote_path: str, host: str = "", username: str = "", port: int = 22, password: str = "", key_path: str = "") -> dict[str, Any]:
        task = task_service.create_task("upload_verify", "remote verification started")
        Thread(target=self._verify_worker, args=(task.task_id, local_path, remote_path, host, username, port, password, key_path), daemon=True).start()
        return {"task_id": task.task_id, "local_path": local_path, "remote_path": remote_path, "host": host, "username": username, "port": port, "auth_mode": self._connection(host, username, remote_path, port, password, key_path).auth_mode}

    def _verify_worker(self, task_id: str, local_path: str, remote_path: str, host: str, username: str, port: int, password: str, key_path: str) -> None:
        local = Path(local_path).expanduser()
        connection = self._connection(host, username, remote_path, port, password, key_path)
        try:
            result = self._remote_verify_connection(local, connection)
            task_service.complete_task(task_id, message="remote verification finished", result=result)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "local_path": str(local), "remote_path": remote_path, "host": host}
            task_service.fail_task(task_id, message="remote verification failed", error=str(exc))

    def _target(self, host: str, username: str, remote_path: str) -> str:
        user_host = self._user_host(host, username)
        if not user_host or not remote_path:
            raise ValueError("host and remote_path are required")
        return f"{user_host}:{remote_path.rstrip('/')}"

    def _connection(self, host: str, username: str, remote_path: str, port: int = 22, password: str = "", key_path: str = "") -> SshConnection:
        return SshConnection(
            host=host.strip(),
            port=int(port or 22),
            username=username.strip(),
            remote_path=(remote_path.strip() or "/"),
            password=password,
            key_path=key_path.strip(),
        )

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

    def _paramiko_available(self) -> bool:
        try:
            import paramiko  # noqa: F401
        except Exception:
            return False
        return True

    def _connect_paramiko(self, connection: SshConnection):
        import paramiko

        hostname = connection.host
        username = connection.username
        if "@" in hostname and not username:
            username, hostname = hostname.split("@", 1)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict[str, Any] = {
            "hostname": hostname,
            "port": int(connection.port),
            "username": username or None,
            "timeout": 10,
            "look_for_keys": not connection.password and not connection.key_path,
            "allow_agent": not connection.password,
        }
        if connection.password:
            kwargs["password"] = connection.password
        if connection.key_path:
            kwargs["key_filename"] = connection.key_path
        client.connect(**kwargs)
        return client

    def _remote_list_paramiko(self, connection: SshConnection) -> dict[str, Any]:
        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                entries = []
                for attr in sorted(sftp.listdir_attr(connection.remote_path), key=lambda item: (not stat.S_ISDIR(int(item.st_mode or 0)), item.filename.lower())):
                    mode = int(attr.st_mode or 0)
                    entries.append({"name": attr.filename, "is_dir": stat.S_ISDIR(mode), "size": int(attr.st_size or 0)})
                return {"ok": True, "path": connection.remote_path, "entries": entries, "auth_mode": connection.auth_mode}
            finally:
                sftp.close()
        finally:
            client.close()

    def _mkdir_paramiko(self, connection: SshConnection, remote_path: str) -> None:
        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                self._ensure_remote_dir(sftp, remote_path)
            finally:
                sftp.close()
        finally:
            client.close()

    def _remote_space_paramiko(self, connection: SshConnection) -> dict[str, Any]:
        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                stats = sftp.statvfs(connection.remote_path)
                block_size = int(getattr(stats, "f_frsize", 0) or getattr(stats, "f_bsize", 0) or 0)
                return {
                    "path": connection.remote_path,
                    "total_bytes": int(stats.f_blocks) * block_size,
                    "free_bytes": int(stats.f_bfree) * block_size,
                    "available_bytes": int(stats.f_bavail) * block_size,
                    "auth_mode": connection.auth_mode,
                }
            except AttributeError:
                return self._remote_space_df_paramiko(client, connection)
            finally:
                sftp.close()
        finally:
            client.close()

    def _remote_space_df_paramiko(self, client, connection: SshConnection) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        _stdin, stdout, stderr = client.exec_command(f"df -PB1 {shlex.quote(connection.remote_path)}", timeout=10)
        output = stdout.read().decode("utf-8", errors="replace")
        error_text = stderr.read().decode("utf-8", errors="replace").strip()
        lines = [line for line in output.splitlines() if line.strip()]
        if len(lines) < 2:
            raise RuntimeError(error_text or f"remote df returned no usable output for {connection.remote_path}")
        columns = lines[-1].split()
        if len(columns) < 6:
            raise RuntimeError(f"remote df output is not parseable: {lines[-1]}")
        total = int(columns[1])
        used = int(columns[2])
        available = int(columns[3])
        return {"path": connection.remote_path, "total_bytes": total, "free_bytes": max(total - used, 0), "available_bytes": available, "auth_mode": connection.auth_mode}

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

    def _rsync_command(self, local_path: Path, target: str, port: int = 22, key_path: str = "") -> list[str]:
        source = str(local_path)
        if local_path.is_dir():
            source = f"{source.rstrip('/')}/"
        command = ["rsync", "-avh", "--progress", "--partial", "--partial-dir=.rsync-partial", "--append-verify"]
        ssh_command = self._rsync_ssh_command(port, key_path)
        if ssh_command:
            command.extend(["-e", ssh_command])
        command.extend([source, target])
        return command

    def _repair_command(self, local_path: Path, target: str, rel_paths: list[str], port: int = 22, key_path: str = "") -> list[str]:
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
        ssh_command = self._rsync_ssh_command(port, key_path)
        if ssh_command:
            command.extend(["-e", ssh_command])
        command.extend(
            [
            "--files-from",
            str(files_from),
            f"{str(source_root).rstrip('/')}/",
            target,
            ]
        )
        return command

    def _rsync_ssh_command(self, port: int = 22, key_path: str = "") -> str:
        parts = ["ssh"]
        if int(port or 22) != 22:
            parts.extend(["-p", str(int(port))])
        if key_path:
            parts.extend(["-i", shlex.quote(key_path)])
        return " ".join(parts) if len(parts) > 1 else ""

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

    def _remote_verify_connection(self, local_path: Path, connection: SshConnection) -> dict[str, Any]:
        if connection.password or connection.key_path:
            return self._remote_verify_paramiko(local_path, connection)
        return self._remote_verify(local_path, connection.target, connection.port)

    def _remote_verify_paramiko(self, local_path: Path, connection: SshConnection) -> dict[str, Any]:
        manifest = UploadManifest().build(local_path)
        missing: list[str] = []
        mismatched: list[str] = []
        checked = 0
        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                for entry in manifest.get("files", []):
                    rel_path = str(entry.get("path", ""))
                    remote_file = self._remote_join(connection.remote_path, rel_path)
                    try:
                        attr = sftp.stat(remote_file)
                    except FileNotFoundError:
                        missing.append(rel_path)
                        continue
                    checked += 1
                    size_ok = int(attr.st_size or 0) == int(entry.get("size_bytes", -1))
                    hash_ok = self._remote_sftp_sha256(sftp, remote_file) == str(entry.get("sha256", ""))
                    if not size_ok or not hash_ok:
                        mismatched.append(rel_path)
            finally:
                sftp.close()
        finally:
            client.close()
        return {
            "ok": not missing and not mismatched,
            "checked": checked,
            "missing": missing,
            "mismatched": mismatched,
            "file_count": manifest.get("file_count", 0),
            "auth_mode": connection.auth_mode,
        }

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

    def _upload_sftp(self, local_path: Path, connection: SshConnection, rel_paths: list[str] | None = None) -> dict[str, Any]:
        source = local_path.expanduser().resolve()
        base, paths = UploadManifest().source_base_and_files(source)
        selected = set(self._safe_relative_paths(rel_paths or []))
        if selected:
            paths = [base / rel_path for rel_path in selected]
        client = self._connect_paramiko(connection)
        uploaded: list[str] = []
        try:
            sftp = client.open_sftp()
            try:
                self._ensure_remote_dir(sftp, connection.remote_path)
                for path in paths:
                    if not path.is_file():
                        continue
                    rel_path = path.relative_to(base).as_posix()
                    remote_file = self._remote_join(connection.remote_path, rel_path)
                    self._ensure_remote_dir(sftp, str(PurePosixPath(remote_file).parent))
                    sftp.put(str(path), remote_file)
                    uploaded.append(rel_path)
            finally:
                sftp.close()
        finally:
            client.close()
        return {"uploaded": uploaded, "uploaded_count": len(uploaded), "auth_mode": connection.auth_mode}

    def _safe_relative_paths(self, rel_paths: list[str]) -> list[str]:
        safe: list[str] = []
        seen: set[str] = set()
        for raw in rel_paths:
            rel = raw.strip().replace("\\", "/")
            parts = PurePosixPath(rel).parts
            if not rel or rel.startswith("/") or ".." in parts:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            safe.append(rel)
        return sorted(safe)

    def _ensure_remote_dir(self, sftp, remote_dir: str) -> None:  # type: ignore[no-untyped-def]
        path = PurePosixPath(remote_dir)
        current = "/" if path.is_absolute() else "."
        for part in path.parts:
            if part in {"/", "."}:
                continue
            current = str(PurePosixPath(current) / part)
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

    def _remote_join(self, remote_root: str, rel_path: str) -> str:
        return str(PurePosixPath(remote_root.rstrip("/")) / PurePosixPath(rel_path))

    def _remote_sftp_sha256(self, sftp, remote_file: str) -> str:  # type: ignore[no-untyped-def]
        digest = hashlib.sha256()
        with sftp.open(remote_file, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _write_files_from(self, rel_paths: list[str]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="robodataset_v3_rsync_", suffix=".txt", delete=False)
        with handle:
            for rel_path in rel_paths:
                handle.write(f"{rel_path}\n")
        return Path(handle.name)


upload_service = UploadService()
