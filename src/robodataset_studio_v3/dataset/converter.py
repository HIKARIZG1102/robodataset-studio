from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

from robodataset_studio_v3.dataset.validator import METADATA_FIELDS


class Hdf5Converter:
    def convert(self, episodes_dir: Path, output_path: Path, config_yaml: str = "") -> Path:
        episode_paths = sorted(episodes_dir.glob("episode_*.npz"))
        return self.convert_episode_paths(episode_paths, output_path, config_yaml)

    def convert_episode_paths(self, episode_paths: list[Path], output_path: Path, config_yaml: str = "") -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(output_path, "w") as h5:
            episodes_group = h5.create_group("episodes")
            for idx, episode_path in enumerate(episode_paths):
                group = episodes_group.create_group(f"{idx:07d}")
                with np.load(episode_path, allow_pickle=True) as data:
                    for field in data.files:
                        if field in METADATA_FIELDS or field.endswith("_metadata"):
                            group.attrs[field] = self._metadata_attr(data[field])
                        else:
                            group.create_dataset(field, data=data[field], compression="gzip")
            meta = h5.create_group("metadata")
            meta.attrs["config_yaml"] = config_yaml
            meta.attrs["dataset_version"] = "0.1.0"
            meta.attrs["num_episodes"] = len(episode_paths)
            streams = h5.create_group("streams")
            streams.attrs["descriptor_json"] = json.dumps({"source": "robodataset_studio"}, ensure_ascii=False)
        return output_path

    def _metadata_attr(self, value: np.ndarray) -> str:
        try:
            if getattr(value, "shape", ()) == ():
                return str(value.item())
        except Exception:
            pass
        return str(value)
