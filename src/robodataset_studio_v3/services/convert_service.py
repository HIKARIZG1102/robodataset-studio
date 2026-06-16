from __future__ import annotations

from pathlib import Path
from typing import Any

from robodataset_studio_v3.services.task_service import task_service


class ConvertService:
    def scan(self, root: str) -> dict[str, Any]:
        base = Path(root).expanduser()
        sessions = []
        if base.exists():
            for path in sorted(item for item in base.iterdir() if item.is_dir()):
                training = path / "training"
                episodes = sorted(training.glob("episode_*.npz")) if training.exists() else []
                if episodes or (path / "dataset_config.yaml").exists() or (path / "collection_config.yaml").exists():
                    sessions.append({"name": path.name, "path": str(path), "episode_count": len(episodes)})
        result = {"root": str(base), "exists": base.exists(), "sessions": sessions}
        task = task_service.run_instant("convert_scan", f"scanned sessions under {base}", result)
        return {"task_id": task.task_id, "result": result}

    def merge(self, sessions: list[str], output_dir: str) -> dict[str, Any]:
        output = Path(output_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        result = {
            "sessions": sessions,
            "output_dir": str(output),
            "message": "merge backend hook is ready; full NPZ merge will reuse validated V2 merge logic",
        }
        task = task_service.run_instant("convert_merge", "merge task prepared", result)
        return {"task_id": task.task_id, "result": result}

    def hdf5(self, sessions: list[str], output_dir: str) -> dict[str, Any]:
        output = Path(output_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        result = {
            "sessions": sessions,
            "output_dir": str(output),
            "message": "HDF5 conversion hook is ready; full conversion will reuse validated V2 converter",
        }
        task = task_service.run_instant("convert_hdf5", "HDF5 conversion task prepared", result)
        return {"task_id": task.task_id, "result": result}


convert_service = ConvertService()
