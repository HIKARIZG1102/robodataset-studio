from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any

import yaml

from robodataset_studio_v3.ros.episode_recorder import RosEpisodeRecorder
from robodataset_studio_v3.services.config_service import ConfigService
from robodataset_studio_v3.services.project_service import project_service
from robodataset_studio_v3.services.task_service import task_service


class RecordingService:
    def __init__(self) -> None:
        self.projects = project_service
        self.configs = ConfigService()
        self.active: dict[str, dict[str, Any]] = {}
        self.recorder = RosEpisodeRecorder()

    def preflight(self, project_key: str) -> dict[str, Any]:
        dataset_config = self.configs.read_dataset_config(self.projects.project_dir(project_key))
        streams = dataset_config.get("streams", [])
        state_keys = dataset_config.get("state", {}).get("keys", [])
        warnings = []
        if not streams:
            warnings.append("no streams configured")
        if not state_keys:
            warnings.append("no state keys configured")
        result = {"project_key": project_key, "streams": len(streams), "state_keys": len(state_keys), "warnings": warnings}
        task = task_service.run_instant("recording_preflight", f"preflight for {project_key}", result)
        return {"task_id": task.task_id, "result": result}

    def start(
        self,
        project_key: str,
        mode: str = "manual",
        duration_sec: float | None = None,
        target_samples: int | None = None,
    ) -> dict[str, Any]:
        project_dir = self.projects.project_dir(project_key)
        dataset_config = self.configs.read_dataset_config(project_dir)
        recording = dataset_config.setdefault("recording", {})
        recording["stop_mode"] = mode
        if duration_sec is not None:
            recording["episode_duration_sec"] = float(duration_sec)
        if target_samples is not None:
            recording["target_samples"] = int(target_samples)
        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir = project_dir / "raw_sessions" / session_name
        training_dir = session_dir / "training"
        training_dir.mkdir(parents=True, exist_ok=True)
        payload = yaml.safe_dump(dataset_config, sort_keys=False, allow_unicode=True)
        (session_dir / "dataset_config.yaml").write_text(payload, encoding="utf-8")
        (session_dir / "collection_config.yaml").write_text(payload, encoding="utf-8")
        task = task_service.create_task("recording", f"recording started for {project_key}")
        cancel_event = Event()
        self.active[project_key] = {"task_id": task.task_id, "session_dir": str(session_dir), "mode": mode, "cancel_event": cancel_event}
        task_service.add_log(task.task_id, f"session: {session_dir}")
        Thread(
            target=self._record_worker,
            args=(project_key, task.task_id, dataset_config, training_dir, cancel_event, duration_sec, target_samples),
            daemon=True,
        ).start()
        return {"task_id": task.task_id, "session_dir": str(session_dir), "mode": mode}

    def stop(self, project_key: str) -> dict[str, Any]:
        state = self.active.get(project_key)
        if state is None:
            task = task_service.run_instant("recording_stop", f"no active recording for {project_key}", {"active": False})
            return {"task_id": task.task_id, "active": False}
        cancel_event = state.get("cancel_event")
        if isinstance(cancel_event, Event):
            cancel_event.set()
        task_service.add_log(state["task_id"], "stop requested")
        return {"task_id": state["task_id"], "active": True, "session_dir": state["session_dir"], "message": "stop requested"}

    def _record_worker(
        self,
        project_key: str,
        task_id: str,
        dataset_config: dict[str, Any],
        training_dir: Path,
        cancel_event: Event,
        duration_sec: float | None,
        target_samples: int | None,
    ) -> None:
        try:
            result = self.recorder.record_episode(
                dataset_config,
                training_dir,
                0,
                duration_sec=duration_sec,
                target_samples=target_samples,
                cancel_event=cancel_event,
            )
            payload = {
                "path": str(result.path),
                "steps": result.steps,
                "streams": result.streams,
                "warnings": result.warnings,
                "session_dir": str(training_dir.parent),
            }
            task_service.complete_task(task_id, message="recording completed", result=payload)
        except Exception as exc:
            task_service.fail_task(task_id, message="recording failed", error=str(exc))
        finally:
            self.active.pop(project_key, None)


recording_service = RecordingService()
