from __future__ import annotations

import json
import os
import time

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from robodataset_studio.dataset.merge_plan import CalvinMergePlanner, CalvinSessionMerger
from robodataset_studio.dataset.recorder import MockRecorder
from robodataset_studio.core.config_library import ConfigLibrary
from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.core.models import ProjectState
from robodataset_studio.ros.episode_recorder import RosEpisodeRecorder, joint_state_to_robot_obs
from robodataset_studio.ros.image_conversion import image_bytes_to_rgb
from robodataset_studio.ui.pages import AppContext, DiscoveryPage, InspectorPage, SettingsPage, UploadPage
from robodataset_studio.ui.main_window import MainWindow
from robodataset_studio.upload.manifest import UploadManifest
from robodataset_studio.upload.ssh_uploader import SshConnection, SshUploader, parse_ssh_target

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
    assert [row["episodes"] for row in plan] == [2, 2]

    merged_training = tmp_path / "merged_calvin" / "task" / "v1" / "training"
    manifest = CalvinSessionMerger().merge(raw_root, merged_training)

    assert manifest["episode_count"] == 4
    assert [path.name for path in sorted(merged_training.glob("episode_*.npz"))] == [
        "episode_0000000.npz",
        "episode_0000001.npz",
        "episode_0000002.npz",
        "episode_0000003.npz",
    ]
    saved_manifest = json.loads((merged_training.parent / "merge_manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["episode_count"] == 4


def test_mock_recorder_writes_calvin_transition_files(tmp_path) -> None:
    path = MockRecorder().record_episode(tmp_path / "training", 0, steps=3)

    assert path.name == "episode_0000000.npz"
    assert (tmp_path / "training" / "episode_0000002.npz").exists()
    assert (tmp_path / "training" / "lang_annotations" / "auto_lang_ann.npy").exists()
    with np.load(path, allow_pickle=True) as data:
        assert data["rgb_static"].shape == (224, 224, 3)
        assert data["robot_obs"].shape == (6,)
        assert data["rel_actions"].shape == (7,)


def test_upload_manifest_roundtrip(tmp_path) -> None:
    payload = tmp_path / "payload.txt"
    payload.write_text("hello dataset\n", encoding="utf-8")

    manifest = UploadManifest()
    manifest_path = manifest.write(tmp_path)
    result = manifest.verify(manifest_path)

    assert result["ok"] is True
    assert result["checked"] == 1
    assert parse_ssh_target("user@example.com:/data/out") == ("user@example.com", "/data/out")


def test_config_library_roundtrip_and_delete(tmp_path) -> None:
    library = ConfigLibrary(tmp_path / "config_library")
    path = library.save_text("widowx default", "project:\n  name: demo\n")

    assert path.name == "widowx_default.yaml"
    assert [config.name for config in library.list_configs()] == ["widowx_default.yaml"]
    assert "name: demo" in library.load_text("widowx default")
    deleted = library.delete("widowx default")
    assert deleted.name == "widowx_default.yaml"
    assert library.list_configs() == []


def test_parse_ssh_target_rejects_missing_remote_path() -> None:
    with pytest.raises(ValueError, match="user@host:/remote/path"):
        parse_ssh_target("user@example.com")


def test_ssh_connection_target_and_auth_mode() -> None:
    connection = SshConnection(
        host="192.168.1.10",
        port=2222,
        username="trainer",
        remote_path="/data/dataset",
        password="secret",
    )

    assert connection.target == "trainer@192.168.1.10:/data/dataset"
    assert connection.auth_mode == "password"


def test_rsync_upload_uses_port_and_key(tmp_path) -> None:
    ctx = AppContext()
    local = tmp_path / "dataset"
    local.mkdir()
    command = SshUploader(ctx.process_manager).rsync_command(
        local,
        "trainer@example.com:/data/out",
        port=2200,
        key_path="/home/user/.ssh/id_rsa",
    )

    assert "-e" in command
    assert "ssh -p 2200 -i /home/user/.ssh/id_rsa" in command


def test_upload_page_builds_connection_from_split_fields() -> None:
    app = QApplication.instance() or QApplication([])
    page = UploadPage(AppContext())
    page.lan_host.setText("10.0.0.5")
    page.wan_host.setText("public.example.com")
    page.port.setValue(2222)
    page.username.setText("robot")
    page.remote_path.setText("/data/calvin")

    connection = page._connection()

    assert app is not None
    assert connection is not None
    assert connection.host == "10.0.0.5"
    assert connection.target == "robot@10.0.0.5:/data/calvin"
    page.password.setText("secret")
    assert page.auth_hint.text() == "auth: password"


def test_upload_page_remote_listing_table() -> None:
    app = QApplication.instance() or QApplication([])
    page = UploadPage(AppContext())

    page._set_remote_listing([{"name": "training", "is_dir": True, "size": 0}])

    assert app is not None
    assert page.remote_files.item(0, 0).text() == "training"
    assert page.remote_files.item(0, 1).text() == "dir"


def test_upload_page_remote_path_breadcrumbs() -> None:
    app = QApplication.instance() or QApplication([])
    page = UploadPage(AppContext())
    page.remote_path.setText("/data/dataset/calvin")

    crumbs = page._remote_path_parts()

    assert app is not None
    assert crumbs == [
        ("/", "/"),
        ("data", "/data"),
        ("dataset", "/data/dataset"),
        ("calvin", "/data/dataset/calvin"),
    ]


def test_joint_state_to_robot_obs_pads_to_output_dim() -> None:
    robot_obs = joint_state_to_robot_obs(["a", "b"], [1.0, 2.0], [0.1], [0.01], 6)
    assert robot_obs.dtype == np.float32
    assert np.allclose(robot_obs, [1.0, 2.0, 0.0, 0.0, 0.0, 0.0])


def test_joint_state_to_robot_obs_respects_joint_order_and_fields() -> None:
    robot_obs = joint_state_to_robot_obs(
        ["elbow", "waist", "shoulder"],
        [3.0, 1.0, 2.0],
        [0.3, 0.1, 0.2],
        [],
        6,
        ["joint_position", "joint_velocity"],
        ["waist", "shoulder", "elbow"],
    )
    assert np.allclose(robot_obs, [1.0, 2.0, 3.0, 0.1, 0.2, 0.3])


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
    assert config["robot"]["joint_count"] == 6
    assert config["robot"]["control"]["enabled"] is False
    assert config["dataset"]["calvin_like_transition_files"] is True
    assert config["dataset"]["language_annotation_file"] == "lang_annotations/auto_lang_ann.npy"
    assert config["environment"]["type"] == "physical"
    assert config["action"]["source"] == "derived_from_robot_obs"
    assert ConfigManager().validate(config) == []


def test_ros_recorder_writes_annotations_and_delta_actions(tmp_path) -> None:
    recorder = RosEpisodeRecorder()
    config = ConfigManager().build_default_config(ProjectState(), [])
    config["instruction"]["text"] = "catch the satellite"
    robot_obs = np.array(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.3, 0.1, 0.0, 0.0, 0.0, 0.0],
        ],
        dtype=np.float32,
    )
    actions = recorder._derive_actions(config, robot_obs, 3)
    assert actions.shape == (3, 7)
    assert np.allclose(actions[0], [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0])

    recorder._write_language_annotations(config, tmp_path / "training", 5, 7)
    annotations = np.load(tmp_path / "training" / "lang_annotations" / "auto_lang_ann.npy", allow_pickle=True).item()
    assert annotations["info"]["indx"] == [[5, 7]]
    assert annotations["language"]["ann"] == ["catch the satellite"]


def test_inspector_manual_preview_fps_survives_restart() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    page = InspectorPage(ctx)
    page.playback_fps.setValue(30)

    page.prepare_preview_playback_start()

    assert app is not None
    assert page._manual_playback_override is True
    assert page._auto_playback_deadline == 0.0
    assert page._effective_playback_fps == 30
    assert page.playback_timer.interval() == 33


def test_discovery_topic_selection_uses_checkboxes() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    page = DiscoveryPage(ctx)
    ctx.last_graph = {
        "nodes": [],
        "topics": [
            {"name": "/camera/side/image_raw", "type": "sensor_msgs/msg/Image"},
            {"name": "/wx250s/joint_states", "type": "sensor_msgs/msg/JointState"},
        ],
        "services": [],
    }
    page.populate_graph(ctx.last_graph)
    page.topics.item(1, 0).setCheckState(Qt.Checked)

    assert app is not None
    assert page._selected_topics() == [ctx.last_graph["topics"][1]]


def test_main_window_has_review_as_separate_step() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    nav_labels = [window.nav.item(index).text() for index in range(window.nav.count())]

    assert app is not None
    assert nav_labels == [
        "1. 配置与 ROS Topic",
        "2. 采集",
        "3. 数据 Review",
        "4. 数据转换",
        "5. 上传",
    ]


def test_settings_language_toggle_updates_state() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    page = SettingsPage(ctx)

    page.toggle_language()

    assert app is not None
    assert ctx.state.language == "en"
    assert page.language.currentText() == "English"


def test_inspector_source_fps_is_separate_from_display_target() -> None:
    app = QApplication.instance() or QApplication([])
    page = InspectorPage(AppContext())
    page.playback_fps.setValue(15)
    page.prepare_preview_playback_start()

    class Worker:
        def __init__(self, received: int) -> None:
            self.received = received

        def frames_received(self) -> int:
            return self.received

    page._preview_worker = Worker(45)  # type: ignore[assignment]
    page._last_source_received = 0
    page._last_camera_fps_at = time.time() - 1.5

    page.update_source_fps()

    assert app is not None
    assert page._manual_playback_override is True
    assert page._effective_playback_fps == 15
    assert page.playback_timer.interval() == 66
    assert "target: 15 manual" in page.camera_fps.text()


def test_inspector_ignores_stale_preview_thread_finish() -> None:
    app = QApplication.instance() or QApplication([])
    page = InspectorPage(AppContext())
    worker = object()
    thread = object()
    page._preview_worker = worker  # type: ignore[assignment]
    page._preview_thread = thread  # type: ignore[assignment]
    page._preview_generation = 2

    page._preview_finished(1)

    assert app is not None
    assert page._preview_worker is worker
    assert page._preview_thread is thread
