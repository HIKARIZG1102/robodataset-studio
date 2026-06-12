from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.ros.episode_recorder import RosEpisodeRecorder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one RoboDataset Studio ROS2 episode in an isolated process.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--episodes-dir", required=True, type=Path)
    parser.add_argument("--episode-index", required=True, type=int)
    parser.add_argument("--duration-sec", type=float, default=None)
    parser.add_argument("--target-samples", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        config = ConfigManager().loads(args.config.read_text(encoding="utf-8"))
        result = RosEpisodeRecorder().record_episode(
            config,
            args.episodes_dir,
            args.episode_index,
            duration_sec=args.duration_sec,
            target_samples=args.target_samples,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "path": str(result.path),
                "steps": int(result.steps),
                "streams": result.streams,
                "warnings": result.warnings,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
