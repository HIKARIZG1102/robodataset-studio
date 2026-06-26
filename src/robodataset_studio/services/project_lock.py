from __future__ import annotations

import fcntl
import os
from pathlib import Path
from threading import Lock
from typing import TextIO


class ProjectLock:
    _guard = Lock()
    _held_paths: set[Path] = set()

    def __init__(self, project_dir: Path, purpose: str) -> None:
        self.project_dir = project_dir
        self.purpose = purpose
        self.path = project_dir / ".robodataset.lock"
        self._key = self.path.resolve()
        self.handle: TextIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._guard:
            if self._key in self._held_paths:
                raise RuntimeError(f"project is already locked by this backend for another operation: {self.project_dir}")
            self._held_paths.add(self._key)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip()
            handle.close()
            with self._guard:
                self._held_paths.discard(self._key)
            detail = f" Current holder: {owner}" if owner else ""
            raise RuntimeError(f"project is already locked for another operation: {self.project_dir}.{detail}") from exc
        except Exception:
            handle.close()
            with self._guard:
                self._held_paths.discard(self._key)
            raise
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} purpose={self.purpose}\n")
        handle.flush()
        os.fsync(handle.fileno())
        self.handle = handle

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.flush()
            os.fsync(self.handle.fileno())
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            with self._guard:
                self._held_paths.discard(self._key)
