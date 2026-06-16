from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

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
            result["ok"] = True
            result["message"] = "upload task prepared; command execution will be enabled after server profile UI is finalized"
        task = task_service.run_instant("upload_repair" if repair else "upload", "upload task prepared", result)
        return {"task_id": task.task_id, "result": result}

    def verify(self, local_path: str, remote_path: str, host: str = "") -> dict[str, Any]:
        result = {
            "local_path": local_path,
            "remote_path": remote_path,
            "host": host,
            "message": "temporary manifest verification hook is ready",
        }
        task = task_service.run_instant("upload_verify", "verify task prepared", result)
        return {"task_id": task.task_id, "result": result}


upload_service = UploadService()
