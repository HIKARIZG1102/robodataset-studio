from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


class SshUploader:
    def __init__(self, process_manager: ProcessManager) -> None:
        self.process_manager = process_manager

    def upload_with_rsync(self, local_path: Path, target: str):
        command = ["rsync", "-avh", "--progress", str(local_path), target]
        return self.process_manager.start(command, "uploader", "UploadPage")

    def test_connection(self, target: str):
        host, _remote_path = parse_ssh_target(target)
        command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, "true"]
        return self.process_manager.start(command, "ssh_test", "UploadPage")

    def verify_remote_manifest(self, manifest_path: Path, target: str):
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
        command = ["ssh", "-o", "BatchMode=yes", host, "python3", "-"]
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
