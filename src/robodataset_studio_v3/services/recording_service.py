from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Any

import numpy as np
import yaml

from robodataset_studio_v3.services.config_service import ConfigService
from robodataset_studio_v3.core.runtime_env import apply_ros_environment, default_ros_setup
from robodataset_studio_v3.ros.image_conversion import is_image_message_type
from robodataset_studio_v3.services.project_service import project_service
from robodataset_studio_v3.services.ros_service import ros_service
from robodataset_studio_v3.services.task_service import task_service


class RecordingService:
    def __init__(self) -> None:
        self.projects = project_service
        self.configs = ConfigService()
        self.active: dict[str, dict[str, Any]] = {}

    def preflight(self, project_key: str) -> dict[str, Any]:
        dataset_config = self.configs.read_dataset_config(self.projects.project_dir(project_key))
        self.configs.sync_dataset_schema(dataset_config)
        streams = dataset_config.get("streams", [])
        state_keys = dataset_config.get("state", {}).get("keys", [])
        warnings = []
        if not streams:
            warnings.append("no streams configured")
        if not state_keys:
            warnings.append("no state keys configured")
        dataset = dataset_config.get("dataset", {}) if isinstance(dataset_config.get("dataset"), dict) else {}
        requires_actions = bool(dataset.get("requires_actions", True))
        if requires_actions and not state_keys:
            warnings.append("dataset requires actions but no JointState state key is configured; recording will use placeholder robot_obs/actions")
        topic_checks = []
        topics: list[str] = []
        for stream in streams if isinstance(streams, list) else []:
            if isinstance(stream, dict) and stream.get("topic"):
                topics.append(str(stream.get("topic")))
        for key in state_keys if isinstance(state_keys, list) else []:
            if isinstance(key, dict) and key.get("source_topic"):
                topics.append(str(key.get("source_topic")))
        for topic in sorted(set(topics)):
            info = ros_service.topic_info(topic)
            echo = ros_service.echo_once(topic)
            hz = ros_service.topic_hz(topic)
            hz_text = str(hz.get("stdout") or "")
            topic_checks.append(
                {
                    "topic": topic,
                    "info_ok": bool(info.get("ok")),
                    "echo_ok": bool(echo.get("ok")),
                    "hz_ok": bool(hz.get("ok") or "average rate:" in hz_text),
                    "hz": self._parse_hz(hz_text),
                    "info_error": "" if info.get("ok") else str(info.get("stderr") or info.get("error") or ""),
                    "echo_error": "" if echo.get("ok") else str(echo.get("stderr") or echo.get("error") or ""),
                    "hz_error": "" if hz.get("ok") or "average rate:" in hz_text else str(hz.get("stderr") or hz.get("error") or ""),
                }
            )
        missing = [row["topic"] for row in topic_checks if not row["info_ok"]]
        silent = [row["topic"] for row in topic_checks if row["info_ok"] and not row["echo_ok"]]
        no_hz = [row["topic"] for row in topic_checks if row["info_ok"] and not row["hz_ok"]]
        if missing:
            warnings.append("topic info failed: " + ", ".join(missing))
        if silent:
            warnings.append("topic echo once failed or timed out: " + ", ".join(silent))
        if no_hz:
            warnings.append("topic hz failed or timed out: " + ", ".join(no_hz))
        result = {
            "project_key": project_key,
            "streams": len(streams) if isinstance(streams, list) else 0,
            "state_keys": len(state_keys) if isinstance(state_keys, list) else 0,
            "topic_checks": topic_checks,
            "warnings": warnings,
            "ok": not warnings,
        }
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
        self.configs.sync_dataset_schema(dataset_config)
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
        stop_file = session_dir / ".recording_stop"
        if stop_file.exists():
            stop_file.unlink()
        task = task_service.create_task("recording", f"recording started for {project_key}")
        process = self._launch_recording_process(session_dir / "dataset_config.yaml", training_dir, stop_file, duration_sec, target_samples)
        self.active[project_key] = {"task_id": task.task_id, "session_dir": str(session_dir), "mode": mode, "stop_file": stop_file, "process": process, "cancelled": False}
        task_service.register_cancel_callback(task.task_id, lambda key=project_key: self.cancel_recording(key))
        task_service.add_log(task.task_id, f"session: {session_dir}")
        Thread(
            target=self._record_worker,
            args=(project_key, task.task_id, process, training_dir, stop_file),
            daemon=True,
        ).start()
        return {"task_id": task.task_id, "session_dir": str(session_dir), "mode": mode}

    def stop(self, project_key: str) -> dict[str, Any]:
        state = self.active.get(project_key)
        if state is None:
            task = task_service.run_instant("recording_stop", f"no active recording for {project_key}", {"active": False})
            return {"task_id": task.task_id, "active": False}
        stop_file = state.get("stop_file")
        if isinstance(stop_file, Path):
            stop_file.touch()
        process = state.get("process")
        if isinstance(process, subprocess.Popen) and process.poll() is None:
            Thread(target=self._terminate_later, args=(process, state["task_id"]), daemon=True).start()
        task_service.add_log(state["task_id"], "stop requested")
        return {"task_id": state["task_id"], "active": True, "session_dir": state["session_dir"], "message": "stop requested"}

    def cancel_recording(self, project_key: str) -> dict[str, Any]:
        state = self.active.get(project_key)
        if state is not None:
            state["cancelled"] = True
        return self.stop(project_key)

    def simulate(self, project_key: str, target_samples: int | None = None) -> dict[str, Any]:
        project_dir = self.projects.project_dir(project_key)
        dataset_config = self.configs.read_dataset_config(project_dir)
        self.configs.sync_dataset_schema(dataset_config)
        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_simulated"
        session_dir = project_dir / "raw_sessions" / session_name
        training_dir = session_dir / "training"
        task = task_service.create_task("recording_simulate", f"simulating listener episode for {project_key}")
        Thread(target=self._simulate_worker, args=(task.task_id, dataset_config, session_dir, training_dir, target_samples), daemon=True).start()
        return {"task_id": task.task_id, "session_dir": str(session_dir), "mode": "simulate"}

    def _record_worker(
        self,
        project_key: str,
        task_id: str,
        process: subprocess.Popen[str],
        training_dir: Path,
        stop_file: Path,
    ) -> None:
        try:
            stdout, stderr = process.communicate()
            for line in (stdout or "").splitlines()[-120:]:
                task_service.add_log(task_id, line)
            for line in (stderr or "").splitlines()[-120:]:
                task_service.add_log(task_id, line)
            payload = self._json_from_output(stdout) or self._json_from_output(stderr) or {}
            payload.setdefault("session_dir", str(training_dir.parent))
            state = self.active.get(project_key, {})
            if process.returncode == 0 and payload.get("ok", True):
                payload.setdefault("path", str(training_dir / "episode_0000000.npz"))
                task_service.complete_task(task_id, message="recording completed", result=payload)
            elif task_service.is_cancelled(task_id) or bool(state.get("cancelled")):
                task_service.cancel_task(task_id)
            else:
                task_service.fail_task(task_id, message="recording failed", error=str(payload.get("error") or stderr or f"exit code {process.returncode}"))
        except Exception as exc:
            task_service.fail_task(task_id, message="recording failed", error=str(exc))
        finally:
            task_service.clear_cancel_callback(task_id)
            self.active.pop(project_key, None)

    def _launch_recording_process(
        self,
        config_path: Path,
        training_dir: Path,
        stop_file: Path,
        duration_sec: float | None,
        target_samples: int | None,
    ) -> subprocess.Popen[str]:
        command = [
            sys.executable,
            "-m",
            "robodataset_studio_v3.ros.record_episode_cli",
            "--config",
            str(config_path),
            "--episodes-dir",
            str(training_dir),
            "--episode-index",
            "0",
            "--stop-file",
            str(stop_file),
        ]
        if duration_sec is not None:
            command.extend(["--duration-sec", str(float(duration_sec))])
        if target_samples is not None:
            command.extend(["--target-samples", str(int(target_samples))])
        env = self._recording_process_env()
        return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

    def _recording_process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        apply_ros_environment(env)
        src_dir = Path(__file__).resolve().parents[3] / "src"
        python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        ros_setup = env.get("ROS_SETUP", default_ros_setup())
        ros_root = Path(ros_setup).resolve().parent if ros_setup else Path("/opt/ros/humble")
        pythonpath_candidates = [
            src_dir,
            ros_root / "local" / "lib" / python_version / "dist-packages",
            ros_root / "lib" / python_version / "site-packages",
        ]
        current_pythonpath = [path for path in env.get("PYTHONPATH", "").split(os.pathsep) if path]
        prepend = [str(path) for path in pythonpath_candidates if path.is_dir() and str(path) not in current_pythonpath]
        env["PYTHONPATH"] = os.pathsep.join([*prepend, *current_pythonpath])
        return env

    def _terminate_later(self, process: subprocess.Popen[str], task_id: str, delay_sec: float = 8.0) -> None:
        try:
            process.wait(timeout=delay_sec)
        except subprocess.TimeoutExpired:
            task_service.add_log(task_id, f"recording subprocess did not stop within {delay_sec:g}s; terminating")
            try:
                process.terminate()
            except Exception:
                return

    def _simulate_worker(self, task_id: str, dataset_config: dict[str, Any], session_dir: Path, training_dir: Path, target_samples: int | None) -> None:
        try:
            training_dir.mkdir(parents=True, exist_ok=True)
            payload = yaml.safe_dump(dataset_config, sort_keys=False, allow_unicode=True)
            (session_dir / "dataset_config.yaml").write_text(payload, encoding="utf-8")
            (session_dir / "collection_config.yaml").write_text(payload, encoding="utf-8")
            recording = dataset_config.get("recording", {}) if isinstance(dataset_config.get("recording"), dict) else {}
            samples = int(target_samples or recording.get("target_samples") or max(int(float(recording.get("sample_rate_hz") or 10) * 2), 2))
            samples = max(samples, 2)
            dataset = dataset_config.get("dataset", {}) if isinstance(dataset_config.get("dataset"), dict) else {}
            requires_actions = bool(dataset.get("requires_actions", True))
            transition_count = samples - 1 if requires_actions else samples
            streams = [item for item in dataset_config.get("streams", []) if isinstance(item, dict)]
            image_streams = [item for item in streams if is_image_message_type(str(item.get("message_type") or ""))]
            state_keys = [
                item
                for item in dataset_config.get("state", {}).get("keys", [])
                if isinstance(item, dict)
            ]
            state_dim = int(dataset_config.get("action", {}).get("dim") or dataset_config.get("robot", {}).get("joint_count") or 7)
            if not state_keys:
                state_keys = [{"name": "robot_obs", "output_dim": state_dim}]
            for index in range(transition_count):
                arrays: dict[str, Any] = {}
                for stream in image_streams:
                    name = self._stream_output_key(stream)
                    arrays[name] = self._simulated_frame(index)
                primary_obs: np.ndarray | None = None
                for state_key in state_keys:
                    key_name = str(state_key.get("name") or "robot_obs")
                    key_dim = int(state_key.get("output_dim") or state_dim)
                    robot_obs = np.linspace(0, 1, max(key_dim, 1), dtype=np.float32) + np.float32(index * 0.01)
                    arrays[key_name] = robot_obs
                    if primary_obs is None or key_name == str(dataset_config.get("action", {}).get("source_state_key") or "robot_obs"):
                        primary_obs = robot_obs
                primary_obs = primary_obs if primary_obs is not None else np.zeros((state_dim,), dtype=np.float32)
                if requires_actions:
                    action_dim = int(dataset_config.get("action", {}).get("dim") or primary_obs.shape[0])
                    action = np.full((max(action_dim, 1),), 0.01, dtype=np.float32)
                    arrays["rel_actions"] = action
                    arrays["actions"] = action.copy()
                arrays["episode_metadata"] = np.array(json.dumps({"mock": True, "transition_index": index, "collection_config": dataset_config}, ensure_ascii=False))
                arrays["collection_config"] = np.array(json.dumps(dataset_config, ensure_ascii=False))
                self._write_npz_atomic(training_dir / f"episode_{index:07d}.npz", arrays)
            metadata = {"mock": True, "steps": transition_count, "collection_config": dataset_config, "session_dir": str(session_dir)}
            (session_dir / "session_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            task_service.complete_task(task_id, message="simulated episode written", result={"ok": True, "session_dir": str(session_dir), "steps": transition_count})
        except Exception as exc:
            task_service.fail_task(task_id, message="simulation failed", error=str(exc))

    def _simulated_frame(self, index: int) -> np.ndarray:
        height, width = 120, 160
        x = np.linspace(0, 255, width, dtype=np.uint8)
        y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = (x[None, :] + index * 3) % 255
        frame[:, :, 1] = (y + index * 5) % 255
        frame[:, :, 2] = 96
        return frame

    def _stream_output_key(self, stream: dict[str, Any]) -> str:
        calvin_key = stream.get("calvin_key")
        if calvin_key is not None and str(calvin_key).strip():
            return str(calvin_key).strip()
        return str(stream.get("name") or stream.get("topic") or "image").strip("/").replace("/", "_")

    def _write_npz_atomic(self, path: Path, arrays: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(".npz.tmp")
        with tmp_path.open("wb") as file:
            np.savez_compressed(file, **arrays)
            file.flush()
            os.fsync(file.fileno())
        tmp_path.replace(path)

    def _parse_hz(self, stdout: str) -> float | None:
        for line in stdout.splitlines():
            if "average rate:" in line:
                try:
                    return float(line.split("average rate:", 1)[1].strip().split()[0])
                except Exception:
                    return None
        return None

    def _json_from_output(self, text: str | None) -> dict[str, Any] | None:
        if not text:
            return None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            return payload if isinstance(payload, dict) else None
        return None


recording_service = RecordingService()
