from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable

from .models import ProcessRecord, now_id


class ProcessManager:
    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._records: dict[str, ProcessRecord] = {}
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    def records(self) -> list[ProcessRecord]:
        return list(self._records.values())

    def start(self, command: list[str], process_type: str, owner_page: str, group_id: str | None = None) -> ProcessRecord:
        group_id = group_id or now_id("group")
        process_id = now_id(f"proc_{process_type}")
        record = ProcessRecord(
            process_id=process_id,
            type=process_type,
            command=command,
            owner_page=owner_page,
            process_group_id=group_id,
        )
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        record.pid = proc.pid
        record.status = "running"
        self._processes[process_id] = proc
        self._records[process_id] = record
        self._pump_stream(process_id, proc.stdout, record.stdout_tail)
        self._pump_stream(process_id, proc.stderr, record.stderr_tail)
        threading.Thread(target=self._waiter, args=(process_id, proc), daemon=True).start()
        self._notify()
        return record

    def _pump_stream(self, process_id: str, stream, tail: list[str]) -> None:
        def run() -> None:
            if stream is None:
                return
            for line in stream:
                tail.append(line.rstrip())
                del tail[:-200]
                self._notify()
        threading.Thread(target=run, daemon=True).start()

    def _waiter(self, process_id: str, proc: subprocess.Popen[str]) -> None:
        return_code = proc.wait()
        record = self._records.get(process_id)
        if record:
            record.status = "exited" if return_code == 0 else "failed"
            record.ended_at = record.ended_at or __import__("datetime").datetime.now()
        self._notify()

    def stop(self, process_id: str, timeout_sec: float = 3.0) -> None:
        proc = self._processes.get(process_id)
        record = self._records.get(process_id)
        if not proc or proc.poll() is not None:
            if record:
                record.status = "exited"
            self._notify()
            return
        if record:
            record.status = "stopping"
        self._notify()
        try:
            os.killpg(proc.pid, signal.SIGINT)
            deadline = time.time() + timeout_sec
            while time.time() < deadline and proc.poll() is None:
                time.sleep(0.05)
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self._notify()

    def stop_all(self) -> None:
        for process_id in list(self._processes):
            self.stop(process_id)

