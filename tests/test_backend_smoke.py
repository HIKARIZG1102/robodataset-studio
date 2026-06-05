from __future__ import annotations

import json

import numpy as np
import pytest

from robodataset_studio.dataset.merge_plan import CalvinMergePlanner, CalvinSessionMerger
from robodataset_studio.dataset.recorder import MockRecorder
from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.core.models import ProjectState
from robodataset_studio.ros.episode_recorder import joint_state_to_robot_obs
from robodataset_studio.ros.image_conversion import image_bytes_to_rgb
from robodataset_studio.upload.manifest import UploadManifest
from robodataset_studio.upload.ssh_uploader import parse_ssh_target


def test_rgb_image_conversion_respects_encoding() -> None:
    rgb = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
    meta = {"encoding": "rgb8", "height": 1, "width": 2, "step": 6}
    converted = image_bytes_to_rgb(rgb.tobytes(), meta)
    assert converted is not None
    assert converted.tolist() == rgb.tolist()

    bgr = np.array([[[3, 2, 1], [6, 5, 4]]], dtype=np.uint8)
    meta["encoding"] = "bgr8"
    converted = image_bytes_to_rgb(bgr.tobytes(), meta)
    assert converted is not None
    assert converted.tolist() == rgb.tolist()


def test_calvin_session_merge_reindexes_episodes(tmp_path) -> None:
    raw_root = tmp_path / "raw_sessions" / "task" / "v1"
    recorder = MockRecorder()
    recorder.record_episode(raw_root / "session_a" / "training", 3, steps=2)
    recorder.record_episode(raw_root / "session_b" / "training", 8, steps=2)

    plan = CalvinMergePlanner().build_plan(raw_root)
    assert [row["episodes"] for row in plan] == [1, 1]

    merged_training = tmp_path / "merged_calvin" / "task" / "v1" / "training"
    manifest = CalvinSessionMerger().merge(raw_root, merged_training)

    assert manifest["episode_count"] == 2
    assert [path.name for path in sorted(merged_training.glob("episode_*.npz"))] == [
        "episode_0000000.npz",
        "episode_0000001.npz",
    ]
    saved_manifest = json.loads((merged_training.parent / "merge_manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["episode_count"] == 2


def test_upload_manifest_roundtrip(tmp_path) -> None:
    payload = tmp_path / "payload.txt"
    payload.write_text("hello dataset\n", encoding="utf-8")

    manifest = UploadManifest()
    manifest_path = manifest.write(tmp_path)
    result = manifest.verify(manifest_path)

    assert result["ok"] is True
    assert result["checked"] == 1
    assert parse_ssh_target("user@example.com:/data/out") == ("user@example.com", "/data/out")


def test_parse_ssh_target_rejects_missing_remote_path() -> None:
    with pytest.raises(ValueError, match="user@host:/remote/path"):
        parse_ssh_target("user@example.com")


def test_joint_state_to_robot_obs_pads_to_output_dim() -> None:
    robot_obs = joint_state_to_robot_obs([1.0, 2.0], [0.1], [0.01], 6)
    assert robot_obs.dtype == np.float32
    assert np.allclose(robot_obs, [1.0, 2.0, 0.1, 0.01, 0.0, 0.0])


def test_default_config_is_listener_only_without_action_topic() -> None:
    topics = [
        {"name": "/camera/front/image_raw", "type": "sensor_msgs/msg/Image"},
        {"name": "/joint_states", "type": "sensor_msgs/msg/JointState"},
    ]
    config = ConfigManager().build_default_config(ProjectState(), topics)

    assert config["runtime"] == {
        "mode": "listener_only",
        "starts_external_nodes": False,
        "publishes_robot_commands": False,
    }
    assert config["robot"]["action_topic"] is None
    assert config["robot"]["control"]["enabled"] is False
    assert ConfigManager().validate(config) == []
