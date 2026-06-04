from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class MockRecorder:
    def record_episode(self, episodes_dir: Path, episode_index: int, steps: int = 24) -> Path:
        episodes_dir.mkdir(parents=True, exist_ok=True)
        path = episodes_dir / f"episode_{episode_index:07d}.npz"
        rgb_static = np.random.randint(0, 255, (steps, 224, 224, 3), dtype=np.uint8)
        rgb_wrist = np.random.randint(0, 255, (steps, 224, 224, 3), dtype=np.uint8)
        robot_obs = np.random.normal(0, 0.1, (steps, 32)).astype(np.float32)
        rel_actions = np.random.normal(0, 0.02, (steps, 7)).astype(np.float32)
        actions = np.cumsum(rel_actions, axis=0).astype(np.float32)
        metadata = json.dumps({"mock": True, "steps": steps})
        np.savez_compressed(
            path,
            rgb_static=rgb_static,
            rgb_wrist=rgb_wrist,
            robot_obs=robot_obs,
            rel_actions=rel_actions,
            actions=actions,
            episode_metadata=np.array(metadata),
        )
        return path

