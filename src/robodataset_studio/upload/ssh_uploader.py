from __future__ import annotations

from pathlib import Path

from robodataset_studio.core.process_manager import ProcessManager


class SshUploader:
    def __init__(self, process_manager: ProcessManager) -> None:
        self.process_manager = process_manager

    def upload_with_rsync(self, local_path: Path, target: str):
        command = ["rsync", "-avh", "--progress", str(local_path), target]
        return self.process_manager.start(command, "uploader", "UploadPage")

