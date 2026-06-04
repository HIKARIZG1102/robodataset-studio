from __future__ import annotations

from pathlib import Path


class CalvinLayoutScanner:
    def scan(self, root: Path) -> dict[str, object]:
        result: dict[str, object] = {
            "root": str(root),
            "exists": root.exists(),
            "raw_sessions": [],
            "merged": [],
            "hdf5": [],
        }
        if not root.exists():
            return result

        result["raw_sessions"] = self._task_versions(root / "raw_sessions")
        result["merged"] = self._task_versions(root / "merged_calvin")
        result["hdf5"] = [str(path.relative_to(root)) for path in sorted((root / "hdf5").glob("**/*.hdf5"))]
        result["hdf5"].extend(str(path.relative_to(root)) for path in sorted((root / "hdf5").glob("**/*.h5")))
        return result

    def _task_versions(self, base: Path) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        if not base.exists():
            return rows
        for task_dir in sorted(path for path in base.iterdir() if path.is_dir()):
            for version_dir in sorted(path for path in task_dir.iterdir() if path.is_dir()):
                rows.append(
                    {
                        "task": task_dir.name,
                        "version": version_dir.name,
                        "path": str(version_dir),
                        "npz_count": self._count_npz(version_dir),
                        "has_hdf5": (version_dir / "training" / "calvin.hdf5").exists(),
                        "has_manifest": (version_dir / "merge_manifest.json").exists(),
                    }
                )
        return rows

    def _count_npz(self, path: Path) -> int:
        return sum(1 for _ in path.glob("**/episode_*.npz"))

