from __future__ import annotations

import json
import shlex
import stat
import subprocess
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from dataclasses import dataclass

from robodataset_studio.core.process_manager import ProcessManager
from robodataset_studio.upload.manifest import UploadManifest


def parse_ssh_target(target: str) -> tuple[str, str]:
    if ":" not in target:
        raise ValueError("SSH target must use user@host:/remote/path format")
    host, remote_path = target.split(":", 1)
    host = host.strip()
    remote_path = remote_path.strip()
    if not host or not remote_path:
        raise ValueError("SSH target must include both host and remote path")
    return host, remote_path.rstrip("/")


@dataclass
class SshConnection:
    host: str
    port: int
    username: str
    remote_path: str
    password: str = ""
    key_path: str = ""

    @property
    def host_with_user(self) -> str:
        return f"{self.username}@{self.host}"

    @property
    def target(self) -> str:
        return f"{self.host_with_user}:{self.remote_path.rstrip('/')}"

    @property
    def auth_mode(self) -> str:
        if self.key_path:
            return "key"
        if self.password:
            return "password"
        return "agent_or_default_key"


class SshUploader:
    def __init__(self, process_manager: ProcessManager) -> None:
        self.process_manager = process_manager

    def upload_with_rsync(self, local_path: Path, target: str, port: int = 22, key_path: str = ""):
        command = self.rsync_command(local_path, target, port, key_path)
        return self.process_manager.start(command, "uploader", "UploadPage")

    def rsync_command(self, local_path: Path, target: str, port: int = 22, key_path: str = "") -> list[str]:
        ssh_command = f"ssh -p {int(port)}"
        if key_path:
            ssh_command += f" -i {shlex.quote(key_path)}"
        source_args = self._rsync_source_args(local_path)
        return [
            "rsync",
            "-avh",
            "--progress",
            "--partial",
            "--append-verify",
            "-e",
            ssh_command,
            *source_args,
            target,
        ]

    def repair_rsync_command(
        self,
        local_path: Path,
        target: str,
        files_from: Path,
        port: int = 22,
        key_path: str = "",
    ) -> list[str]:
        ssh_command = f"ssh -p {int(port)}"
        if key_path:
            ssh_command += f" -i {shlex.quote(key_path)}"
        source_root = local_path.parent if local_path.is_file() else local_path
        return [
            "rsync",
            "-avh",
            "--progress",
            "--partial",
            "--append-verify",
            "--files-from",
            str(files_from),
            "-e",
            ssh_command,
            f"{str(source_root).rstrip('/')}/",
            target,
        ]

    def upload_connection_with_rsync(self, local_path: Path, connection: SshConnection):
        return self.upload_with_rsync(local_path, connection.target, connection.port, connection.key_path)

    def repair_resume_connection_with_rsync(self, local_path: Path, connection: SshConnection, files_from: Path):
        command = self.repair_rsync_command(local_path, connection.target, files_from, connection.port, connection.key_path)
        return self.process_manager.start(command, "uploader", "UploadPage")

    def upload_connection_with_sftp(
        self,
        local_path: Path,
        connection: SshConnection,
        rel_paths: list[str] | None = None,
    ) -> dict[str, Any]:
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
        return {"uploaded": uploaded, "uploaded_count": len(uploaded)}

    def _rsync_source_args(self, local_path: Path) -> list[str]:
        source = local_path.expanduser()
        if source.is_file():
            return [str(source)]
        return [f"{str(source).rstrip('/')}/"]

    def test_connection(self, target: str, port: int = 22, key_path: str = ""):
        host, _remote_path = parse_ssh_target(target)
        command = ["ssh", "-p", str(int(port)), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
        if key_path:
            command.extend(["-i", key_path])
        command.extend([host, "true"])
        return self.process_manager.start(command, "ssh_test", "UploadPage")

    def list_remote_dir(self, connection: SshConnection) -> list[dict[str, Any]]:
        import paramiko

        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                entries = []
                for attr in sorted(sftp.listdir_attr(connection.remote_path), key=lambda item: item.filename):
                    mode = int(attr.st_mode or 0)
                    entries.append(
                        {
                            "name": attr.filename,
                            "is_dir": stat.S_ISDIR(mode),
                            "size": int(attr.st_size or 0),
                        }
                    )
                return entries
            finally:
                sftp.close()
        finally:
            client.close()

    def mkdir_remote(self, connection: SshConnection, folder_name: str) -> str:
        import paramiko

        folder = folder_name.strip().strip("/")
        if not folder or "/" in folder:
            raise ValueError("folder name must be a single directory name")
        remote_path = f"{connection.remote_path.rstrip('/')}/{folder}"
        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                sftp.mkdir(remote_path)
            finally:
                sftp.close()
        finally:
            client.close()
        return remote_path

    def remote_space(self, connection: SshConnection) -> dict[str, int]:
        client = self._connect_paramiko(connection)
        try:
            sftp = client.open_sftp()
            try:
                stats = sftp.statvfs(connection.remote_path)
                block_size = int(getattr(stats, "f_frsize", 0) or getattr(stats, "f_bsize", 0) or 0)
                total = int(stats.f_blocks) * block_size
                free = int(stats.f_bfree) * block_size
                available = int(stats.f_bavail) * block_size
                return {
                    "total_bytes": total,
                    "free_bytes": free,
                    "available_bytes": available,
                }
            except AttributeError:
                return self._remote_space_with_df(client, connection.remote_path)
            finally:
                sftp.close()
        finally:
            client.close()

    def _remote_space_with_df(self, client, remote_path: str) -> dict[str, int]:  # type: ignore[no-untyped-def]
        command = f"df -PB1 {shlex.quote(remote_path)}"
        _stdin, stdout, stderr = client.exec_command(command, timeout=10)
        output = stdout.read().decode("utf-8", errors="replace")
        error_text = stderr.read().decode("utf-8", errors="replace").strip()
        lines = [line for line in output.splitlines() if line.strip()]
        if len(lines) < 2:
            raise RuntimeError(error_text or f"remote df returned no usable output for {remote_path}")
        columns = lines[-1].split()
        if len(columns) < 6:
            raise RuntimeError(f"remote df output is not parseable: {lines[-1]}")
        total = int(columns[1])
        used = int(columns[2])
        available = int(columns[3])
        return {
            "total_bytes": total,
            "free_bytes": max(total - used, 0),
            "available_bytes": available,
        }

    def _connect_paramiko(self, connection: SshConnection):
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict[str, Any] = {
            "hostname": connection.host,
            "port": int(connection.port),
            "username": connection.username,
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

    def verify_remote_manifest(self, manifest_path: Path, target: str, port: int = 22, key_path: str = ""):
        host, remote_path = parse_ssh_target(target)
        checks = self._manifest_checks(manifest_path, remote_path)
        script = self._remote_verify_script(checks)
        command = ["ssh", "-p", str(int(port)), "-o", "BatchMode=yes"]
        if key_path:
            command.extend(["-i", key_path])
        command.extend([host, "python3", "-"])
        record = self.process_manager.start(command, "ssh_verify", "UploadPage")
        proc = self.process_manager.process(record.process_id)
        if proc and proc.stdin:
            proc.stdin.write(script)
            proc.stdin.close()
        return record

    def remote_manifest_result(self, manifest_path: Path, target: str, port: int = 22, key_path: str = "") -> dict[str, Any]:
        host, remote_path = parse_ssh_target(target)
        checks = self._manifest_checks(manifest_path, remote_path)
        script = self._remote_verify_script(checks)
        command = ["ssh", "-p", str(int(port)), "-o", "BatchMode=yes"]
        if key_path:
            command.extend(["-i", key_path])
        command.extend([host, "python3", "-"])
        completed = subprocess.run(command, input=script, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            detail = "\n".join(part.strip() for part in [completed.stderr, completed.stdout] if part.strip())
            raise RuntimeError(detail or f"remote manifest verification exited with code {completed.returncode}")
        return self._parse_json_result(completed.stdout)

    def remote_manifest_result_connection(self, manifest_path: Path, connection: SshConnection) -> dict[str, Any]:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        }

    def repair_paths_from_result(self, result: dict[str, Any]) -> list[str]:
        paths = []
        for key in ("missing", "mismatched"):
            value = result.get(key, [])
            if isinstance(value, list):
                paths.extend(str(item) for item in value)
        return self._safe_relative_paths(paths)

    def write_files_from(self, rel_paths: list[str]) -> Path:
        safe_paths = self._safe_relative_paths(rel_paths)
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="robodataset_rsync_files_", suffix=".txt", delete=False)
        with handle:
            for rel_path in safe_paths:
                handle.write(f"{rel_path}\n")
        return Path(handle.name)

    def _manifest_checks(self, manifest_path: Path, remote_path: str) -> list[dict[str, Any]]:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks = []
        for entry in manifest.get("files", []):
            rel_path = str(entry.get("path", ""))
            sha256 = str(entry.get("sha256", ""))
            size = int(entry.get("size_bytes", -1))
            remote_file = f"{remote_path.rstrip('/')}/{rel_path}"
            checks.append(
                {
                    "path": rel_path,
                    "remote": remote_file,
                    "sha256": sha256,
                    "size_bytes": size,
                }
            )
        return checks

    def _parse_json_result(self, text: str) -> dict[str, Any]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end < start:
                raise RuntimeError(text.strip() or "remote verification returned no JSON result")
            payload = json.loads(text[start : end + 1])
        if not isinstance(payload, dict):
            raise RuntimeError("remote verification returned non-object JSON")
        return payload

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
        import hashlib

        digest = hashlib.sha256()
        with sftp.open(remote_file, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

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
    hash_ok = digest.hexdigest() == entry["sha256"]
    if not size_ok or not hash_ok:
        mismatched.append(entry["path"])
result = {{
    "ok": not missing and not mismatched,
    "checked": checked,
    "missing": missing,
    "mismatched": mismatched,
}}
print(json.dumps(result, ensure_ascii=False, indent=2))
"""
