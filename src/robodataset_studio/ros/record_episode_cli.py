from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from threading import Event

from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.ros.episode_recorder import RosEpisodeRecorder


class StopFileEvent(Event):
    def __init__(self, stop_file: Path | None) -> None:
        super().__init__()
        self.stop_file = stop_file

    def is_set(self) -> bool:
        return super().is_set() or bool(self.stop_file and self.stop_file.exists())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one RoboDataset Studio ROS2 episode in an isolated process.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--episodes-dir", required=True, type=Path)
    parser.add_argument("--episode-index", required=True, type=int)
    parser.add_argument("--duration-sec", type=float, default=None)
    parser.add_argument("--target-samples", type=int, default=None)
    parser.add_argument("--stop-file", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        config = ConfigManager().loads(args.config.read_text(encoding="utf-8"))
        cancel_event = StopFileEvent(args.stop_file) if args.stop_file is not None else None
        result = RosEpisodeRecorder().record_episode(
            config,
            args.episodes_dir,
            args.episode_index,
            duration_sec=args.duration_sec,
            target_samples=args.target_samples,
            cancel_event=cancel_event,
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
