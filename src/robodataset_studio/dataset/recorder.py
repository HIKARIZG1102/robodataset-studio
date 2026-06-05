from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np


class MockRecorder:
    def record_episode(self, episodes_dir: Path, episode_index: int, steps: int = 24) -> Path:
        episodes_dir.mkdir(parents=True, exist_ok=True)
        path = episodes_dir / f"episode_{episode_index:07d}.npz"
        transition_count = max(steps, 1)
        for offset in range(transition_count):
            rgb_static = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
            rgb_wrist = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
            robot_obs = np.random.normal(0, 0.1, (6,)).astype(np.float32)
            rel_actions = np.random.normal(0, 0.02, (7,)).astype(np.float32)
            metadata = json.dumps({"mock": True, "transition_index": offset})
            np.savez_compressed(
                episodes_dir / f"episode_{episode_index + offset:07d}.npz",
                rgb_static=rgb_static,
                rgb_wrist=rgb_wrist,
                robot_obs=robot_obs,
                rel_actions=rel_actions,
                actions=rel_actions.copy(),
                episode_metadata=np.array(metadata),
            )
        self._write_annotations(episodes_dir, episode_index, episode_index + transition_count - 1)
        return path

    def _write_annotations(self, episodes_dir: Path, start_idx: int, end_idx: int) -> None:
        ann_path = episodes_dir / "lang_annotations" / "auto_lang_ann.npy"
        ann_path.parent.mkdir(parents=True, exist_ok=True)
        annotations = {
            "info": {"indx": [[start_idx, end_idx]]},
            "language": {"ann": ["mock listener episode"], "task": ["mock_listener_episode"]},
        }
        tmp_path = ann_path.with_suffix(".npy.tmp")
        with tmp_path.open("wb") as file:
            np.save(file, annotations, allow_pickle=True)
            file.flush()
            os.fsync(file.fileno())
        tmp_path.replace(ann_path)
