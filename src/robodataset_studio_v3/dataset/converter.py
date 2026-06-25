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
                        value = data[field]
                        if field in METADATA_FIELDS or field.endswith("_metadata"):
                            group.attrs[field] = self._metadata_attr(value)
                        else:
                            self._create_dataset(group, field, value)
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

    def _create_dataset(self, group: h5py.Group, field: str, value: np.ndarray) -> None:
        array = np.asarray(value)
        original_dtype = str(array.dtype)
        if array.dtype.kind in {"U", "S"}:
            dataset = group.create_dataset(field, data=self._utf8_array(array), dtype=h5py.string_dtype(encoding="utf-8"))
        elif array.dtype.kind == "O":
            dataset = group.create_dataset(field, data=self._object_array_to_utf8(array), dtype=h5py.string_dtype(encoding="utf-8"))
        elif array.shape == ():
            dataset = group.create_dataset(field, data=array)
        else:
            dataset = group.create_dataset(field, data=array, compression="gzip")
        dataset.attrs["source_dtype"] = original_dtype

    def _utf8_array(self, array: np.ndarray) -> np.ndarray:
        if array.shape == ():
            return np.asarray(str(array.item()), dtype=object)
        return array.astype(object)

    def _object_array_to_utf8(self, array: np.ndarray) -> np.ndarray:
        def normalize(value: object) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value)

        if array.shape == ():
            return np.asarray(normalize(array.item()), dtype=object)
        return np.vectorize(normalize, otypes=[object])(array)
