from __future__ import annotations

import json
import shlex
import stat
from pathlib import Path
from typing import Any
from dataclasses import dataclass

from robodataset_studio.core.process_manager import ProcessManager


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
        return ["rsync", "-avh", "--progress", "-e", ssh_command, str(local_path), target]

    def upload_connection_with_rsync(self, local_path: Path, connection: SshConnection):
        return self.upload_with_rsync(local_path, connection.target, connection.port, connection.key_path)

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
            finally:
                sftp.close()
        finally:
            client.close()

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
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks = []
        for entry in manifest.get("files", []):
            rel_path = str(entry.get("path", ""))
            sha256 = str(entry.get("sha256", ""))
            size = int(entry.get("size_bytes", -1))
            remote_file = f"{remote_path}/{rel_path}"
            checks.append(
                {
                    "path": rel_path,
                    "remote": remote_file,
                    "sha256": sha256,
                    "size_bytes": size,
                }
            )
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
