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
from robodataset_studio.dataset.validator import DatasetValidator
from robodataset_studio.core.config_library import ConfigLibrary
from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.core.models import ProjectState
from robodataset_studio.core.settings_store import UserSettingsStore
from robodataset_studio.ros.episode_recorder import RosEpisodeRecorder, joint_state_to_robot_obs
from robodataset_studio.ros.image_conversion import image_bytes_to_rgb
from robodataset_studio.ui.pages import AppContext, ConfigPage, DiscoveryPage, InspectorPage, RecordingPage, ReviewPage, SettingsPage, UploadPage
from robodataset_studio.ui.main_window import MainWindow
from robodataset_studio.upload.manifest import UploadManifest
from robodataset_studio.upload.ssh_uploader import SshConnection, SshUploader, parse_ssh_target
from robodataset_studio.upload.ssh_profiles import SshProfile, SshProfileStore

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_user_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


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


def test_ros_recorder_sample_count_controls_transition_count(tmp_path) -> None:
    recorder = RosEpisodeRecorder()
    config = ConfigManager().build_default_config(
        ProjectState(),
        [
            {"name": "/camera/front/image_raw", "type": "sensor_msgs/msg/Image"},
            {"name": "/joint_states", "type": "sensor_msgs/msg/JointState"},
        ],
    )
    config["recording"]["stop_mode"] = "sample_count"
    config["recording"]["target_samples"] = 6

    def capture_streams(image_streams, joint_streams, steps, sample_rate):  # type: ignore[no-untyped-def]
        frames = {
            "rgb_static": [
                np.full((4, 4, 3), index, dtype=np.uint8)
                for index in range(steps)
            ]
        }
        states = {"robot_obs": [np.full((3,), index, dtype=np.float32) for index in range(steps)]}
        return frames, states

    recorder._capture_streams = capture_streams  # type: ignore[method-assign]
    result = recorder.record_episode(config, tmp_path / "training", 0)

    assert result.steps == 5
    assert len(list((tmp_path / "training").glob("episode_*.npz"))) == 5
    with np.load(tmp_path / "training" / "episode_0000004.npz", allow_pickle=True) as data:
        assert data["rgb_static"].shape == (4, 4, 3)
        assert data["rel_actions"].shape == (3,)


def test_dataset_validator_flags_black_frame_quality_issue(tmp_path) -> None:
    training = tmp_path / "training"
    training.mkdir()
    path = training / "episode_0000000.npz"
    np.savez_compressed(
        path,
        rgb_static=np.zeros((224, 224, 3), dtype=np.uint8),
        rgb_wrist=np.full((224, 224, 3), 128, dtype=np.uint8),
        robot_obs=np.zeros((6,), dtype=np.float32),
        rel_actions=np.zeros((7,), dtype=np.float32),
        actions=np.zeros((7,), dtype=np.float32),
    )

    rows = DatasetValidator().scan_npz(training)
    detail = DatasetValidator().describe_npz(path)

    assert rows[0]["status"] == "warning"
    assert rows[0]["quality"] == "black_frame:rgb_static"
    assert "quality_issues: black_frame:rgb_static" in detail


def test_dataset_validator_uses_config_required_image_keys(tmp_path) -> None:
    training = tmp_path / "training"
    training.mkdir()
    path = training / "episode_0000000.npz"
    np.savez_compressed(
        path,
        rgb_static=np.full((224, 224, 3), 128, dtype=np.uint8),
        robot_obs=np.zeros((6,), dtype=np.float32),
        rel_actions=np.zeros((7,), dtype=np.float32),
        actions=np.zeros((7,), dtype=np.float32),
    )
    config = {
        "streams": [
            {
                "name": "rgb_static",
                "calvin_key": "rgb_static",
                "message_type": "sensor_msgs/msg/Image",
                "required": True,
            }
        ]
    }

    rows = DatasetValidator().scan_npz(training, config)
    detail = DatasetValidator().describe_npz(path, config)

    assert rows[0]["status"] == "ok"
    assert rows[0]["missing"] == ""
    assert "missing_required: -" in detail


def test_dataset_validator_quality_report_counts_status_issues_and_marks() -> None:
    rows = [
        {"name": "episode_0000000.npz", "path": "a", "status": "ok", "quality": "-", "missing": ""},
        {
            "name": "episode_0000001.npz",
            "path": "b",
            "status": "warning",
            "quality": "black_frame:rgb_static, action_dim:actions=6",
            "missing": "",
        },
    ]

    report = DatasetValidator().quality_report(rows, {"episode_0000001.npz": "bad"})

    assert report["total"] == 2
    assert report["by_status"] == {"ok": 1, "warning": 1, "error": 0}
    assert report["issue_counts"] == {"action_dim:actions=6": 1, "black_frame:rgb_static": 1}
    assert report["mark_counts"] == {"bad": 1, "unmarked": 1}


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


def test_ssh_profile_store_roundtrip_without_password(tmp_path) -> None:
    store = SshProfileStore(tmp_path / "ssh_profiles.json")
    store.save_profile(
        SshProfile(
            name="lab server",
            lan_host="10.0.0.8",
            wan_host="public.example.com",
            port=2200,
            username="robot",
            key_path="/home/robot/.ssh/id_rsa",
            remote_path="/data/calvin",
        )
    )

    profile = store.load_profile("lab server")
    raw = (tmp_path / "ssh_profiles.json").read_text(encoding="utf-8")

    assert profile.lan_host == "10.0.0.8"
    assert profile.port == 2200
    assert profile.remote_path == "/data/calvin"
    assert "password" not in raw.lower()


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


def test_upload_page_saves_and_loads_server_profile_without_password(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.ssh_profiles = SshProfileStore(tmp_path / "ssh_profiles.json")
    page = UploadPage(ctx)
    page.profile_name.setText("lab server")
    page.lan_host.setText("10.0.0.5")
    page.wan_host.setText("public.example.com")
    page.port.setValue(2222)
    page.username.setText("robot")
    page.password.setText("secret")
    page.key_path.setText("/home/robot/.ssh/id_rsa")
    page.remote_path.setText("/data/calvin")

    page.save_server_profile()
    page.lan_host.clear()
    page.password.setText("still-local")
    page.load_server_profile()

    assert app is not None
    assert page.profile_select.currentText() == "lab server"
    assert page.lan_host.text() == "10.0.0.5"
    assert page.password.text() == ""
    assert page.key_path.text() == "/home/robot/.ssh/id_rsa"


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


def test_upload_page_local_size_and_format_bytes(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    local = tmp_path / "dataset"
    nested = local / "training"
    nested.mkdir(parents=True)
    (local / "a.bin").write_bytes(b"12345")
    (nested / "b.bin").write_bytes(b"1234567")
    page = UploadPage(AppContext())

    assert app is not None
    assert page._local_size_bytes(local) == 12
    assert page._format_bytes(1536) == "1.50 KB"


def test_upload_page_parses_rsync_progress() -> None:
    app = QApplication.instance() or QApplication([])
    page = UploadPage(AppContext())

    summary = page._parse_rsync_progress(
        [
            "sending incremental file list",
            "training/episode_0000001.npz",
            "     12,345,678  45%   12.34MB/s    0:00:03",
        ]
    )

    assert app is not None
    assert summary == {
        "file": "training/episode_0000001.npz",
        "percent": 45,
        "speed": "12.34MB/s",
        "eta": "0:00:03",
    }


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
    assert config["robot"]["joint_count"] == 0
    assert config["robot"]["joint_order"] == []
    assert config["robot"]["control"]["enabled"] is False
    assert config["dataset"]["calvin_like_transition_files"] is True
    assert config["dataset"]["language_annotation_file"] == "lang_annotations/auto_lang_ann.npy"
    assert config["environment"]["type"] == "physical"
    assert config["environment"]["description"] == ""
    assert config["instruction"]["text"] == ""
    assert config["instruction"]["success_condition"] == ""
    assert "ai_validation" not in config
    assert config["action"]["source"] == "derived_from_robot_obs"
    assert config["action"]["dim"] == 0
    assert config["state"]["keys"][0]["source_topic"] == "/joint_states"
    assert config["state"]["keys"][0]["output_dim"] == 0
    assert ConfigManager().validate(config) == []


def test_default_config_maps_pi05_camera_topics_to_static_and_wrist() -> None:
    topics = [
        {"name": "/camera/camera_wrist/color/image_raw", "type": "sensor_msgs/msg/Image"},
        {"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"},
        {"name": "/wx250s/joint_states", "type": "sensor_msgs/msg/JointState"},
    ]

    config = ConfigManager().build_default_config(ProjectState(), topics)
    streams = {stream["name"]: stream for stream in config["streams"]}

    assert streams["rgb_static"]["topic"] == "/camera/camera/color/image_raw"
    assert streams["rgb_static"]["calvin_key"] == "rgb_static"
    assert streams["rgb_wrist"]["topic"] == "/camera/camera_wrist/color/image_raw"
    assert streams["rgb_wrist"]["calvin_key"] == "rgb_wrist"
    assert config["state"]["keys"][0]["source_topic"] == "/wx250s/joint_states"
    assert config["dataset"]["requires_robot_obs"] is True
    assert config["dataset"]["requires_actions"] is True


def test_default_config_keeps_camera_only_selection_camera_only() -> None:
    topics = [
        {"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"},
        {"name": "/camera/camera/depth/image_rect_raw", "type": "sensor_msgs/msg/Image"},
    ]

    config = ConfigManager().build_default_config(ProjectState(), topics)
    streams = {stream["name"]: stream for stream in config["streams"]}

    assert config["state"]["keys"] == []
    assert config["action"]["source"] == "not_configured"
    assert config["dataset"]["requires_robot_obs"] is False
    assert config["dataset"]["requires_actions"] is False
    assert streams["rgb_static"]["topic"] == "/camera/camera/color/image_raw"
    assert streams["rgb_static"]["modality"] == "rgb"
    assert streams["depth_1"]["topic"] == "/camera/camera/depth/image_rect_raw"
    assert streams["depth_1"]["modality"] == "depth"
    assert streams["depth_1"]["calvin_key"] is None
    assert "ai_validation" not in config


def test_command_joint_group_topic_is_not_treated_as_joint_state() -> None:
    topics = [
        {"name": "/camera/camera_wrist/color/image_raw", "type": "sensor_msgs/msg/Image"},
        {"name": "/wx250s/commands/joint_group", "type": "interbotix_xs_msgs/msg/JointGroupCommand"},
    ]

    config = ConfigManager().build_default_config(ProjectState(), topics)

    assert config["robot"]["joint_state_topic"] is None
    assert config["state"]["keys"] == []
    assert config["action"]["source"] == "not_configured"
    assert config["dataset"]["requires_robot_obs"] is False
    assert config["dataset"]["requires_actions"] is False


def test_default_config_supports_more_than_four_image_tracks() -> None:
    topics = [
        {"name": f"/camera/cam_{index}/color/image_raw", "type": "sensor_msgs/msg/Image"}
        for index in range(6)
    ]

    config = ConfigManager().build_default_config(ProjectState(), topics)

    assert len(config["streams"]) == 6
    assert [stream["calvin_key"] for stream in config["streams"]] == [
        "rgb_static",
        "rgb_1",
        "rgb_2",
        "rgb_3",
        "rgb_4",
        "rgb_5",
    ]


def test_config_validation_requires_joint_state_key() -> None:
    config = ConfigManager().build_default_config(ProjectState(), None)
    config["dataset"]["requires_robot_obs"] = True
    config["state"]["keys"] = []

    errors = ConfigManager().validate(config)

    assert "missing required JointState state key for robot_obs" in errors


def test_empty_topic_selection_generates_empty_streams_not_template_defaults() -> None:
    config = ConfigManager().build_default_config(ProjectState(), [])

    assert config["streams"] == []
    assert config["cameras"] == []
    assert config["state"]["keys"] == []
    assert config["dataset"]["requires_robot_obs"] is False
    assert ConfigManager().validate(config) == ["missing cameras or streams"]


def test_config_loader_drops_legacy_ai_validation_section() -> None:
    config = ConfigManager().loads(
        """
project:
  name: demo
ai_validation:
  base_url: https://api.example.com/v1
  api_key_env: ROBOT_DATA_AI_API_KEY
"""
    )

    assert config == {"project": {"name": "demo"}}


def test_config_page_quick_form_updates_yaml() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
    )
    page = ConfigPage(ctx)

    page.instruction.setText("pick up the white cube")
    page.instruction_language.setText("en")
    page.task_family.setText("manipulation")
    page.success_condition.setText("cube is lifted")
    page.scene_description.setPlainText("physical tabletop scene with one white cube")
    page.project_name.setText("cube_task")
    page.project_version.setText("v2")
    page.project_operator.setText("tester")
    page.project_environment.setText("physical")
    page.environment_type.setText("physical")
    page.environment_workspace.setText("robotarm_control_ws")
    page.environment_lighting.setText("lab")
    page.environment_objects.setText("white cube, table")
    page.environment_notes.setPlainText("notes here")
    page.robot_name.setText("test_arm")
    page.robot_model.setText("generic")
    page.robot_description.setText("generic arm")
    page.robot_joint_count.setValue(7)
    page.robot_joint_order.setText("j1, j2, j3")
    page.robot_base_frame.setText("base")
    page.robot_ee_frame.setText("ee")
    page.sample_rate.setValue(15)
    page.stop_mode.setCurrentIndex(page.stop_mode.findData("sample_count"))
    page.episode_duration.setValue(0.5)
    page.target_samples.setValue(8)
    page.crop_enabled.setChecked(True)
    page.crop_x.setValue(10)
    page.crop_y.setValue(20)
    page.crop_width.setValue(320)
    page.crop_height.setValue(240)
    page.resize_enabled.setChecked(True)
    page.resize_width.setValue(256)
    page.resize_height.setValue(256)

    page.apply_form_to_yaml()
    config = ctx.config_manager.loads(page.editor.toPlainText())

    assert app is not None
    assert config["project"]["name"] == "cube_task"
    assert config["project"]["version"] == "v2"
    assert config["project"]["operator"] == "tester"
    assert config["project"]["environment"] == "physical"
    assert config["instruction"]["text"] == "pick up the white cube"
    assert config["instruction"]["language"] == "en"
    assert config["instruction"]["task_family"] == "manipulation"
    assert config["instruction"]["success_condition"] == "cube is lifted"
    assert config["environment"]["description"] == "physical tabletop scene with one white cube"
    assert config["environment"]["workspace"] == "robotarm_control_ws"
    assert config["environment"]["lighting"] == "lab"
    assert config["environment"]["objects"] == ["white cube", "table"]
    assert config["environment"]["notes"] == "notes here"
    assert config["robot"]["name"] == "test_arm"
    assert config["robot"]["model"] == "generic"
    assert config["robot"]["description"] == "generic arm"
    assert config["robot"]["joint_count"] == 7
    assert config["robot"]["joint_order"] == ["j1", "j2", "j3"]
    assert config["robot"]["base_frame"] == "base"
    assert config["robot"]["end_effector_frame"] == "ee"
    assert config["recording"]["sample_rate_hz"] == 15
    assert config["recording"]["stop_mode"] == "sample_count"
    assert config["recording"]["episode_duration_sec"] == 0.5
    assert config["recording"]["target_samples"] == 8
    assert config["cameras"][0]["crop"] == {"enabled": True, "x": 10, "y": 20, "width": 320, "height": 240}
    assert config["cameras"][0]["resize"] == {"enabled": True, "width": 256, "height": 256}
    assert config["streams"][0]["preview"]["crop"]["width"] == 320
    assert "ai_validation" not in config


def test_config_page_refresh_from_selected_topics_updates_yaml_and_preview() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.selected_streams = [{"name": "/camera/front/image_raw", "type": "sensor_msgs/msg/Image"}]
    page = ConfigPage(ctx)
    page.instruction.setText("move the cube")

    page.refresh_config_from_selected_topics()
    config = ctx.config_manager.loads(page.editor.toPlainText())

    assert app is not None
    assert config["streams"][0]["topic"] == "/camera/front/image_raw"
    assert config["state"]["keys"] == []
    assert config["instruction"]["text"] == "move the cube"
    assert config["dataset"]["requires_robot_obs"] is False
    assert "/camera/front/image_raw" in page.selected_topics_view.toPlainText()
    assert "episode_0000000.npz" in page.dataset_preview.toPlainText()


def test_ros_recorder_writes_annotations_and_delta_actions(tmp_path) -> None:
    recorder = RosEpisodeRecorder()
    config = ConfigManager().build_default_config(ProjectState(), None)
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
    assert actions.shape == (3, 6)
    assert np.allclose(actions[0], [0.1, 0.0, 0.0, 0.0, 0.0, 0.0])

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


def test_recording_page_populates_capture_monitor_topics() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [
            {"name": "/camera/front/image_raw", "type": "sensor_msgs/msg/Image"},
            {"name": "/joint_states", "type": "sensor_msgs/msg/JointState"},
        ],
    )
    page = RecordingPage(ctx)

    assert app is not None
    assert len(page._monitor_slots) == 1
    assert page._monitor_slots[0].topic == "/camera/front/image_raw"
    page.close()


def test_recording_page_limits_capture_monitors_to_four() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = {
        "runtime": {"mode": "listener_only"},
        "streams": [
            {
                "name": f"rgb_{index}",
                "topic": f"/camera/{index}/image_raw",
                "message_type": "sensor_msgs/msg/Image",
                "modality": "rgb",
                "source": "ros2_topic",
                "training_role": "observation",
            }
            for index in range(5)
        ],
    }
    page = RecordingPage(ctx)

    assert app is not None
    assert len(page._monitor_slots) == 4
    assert [slot.topic for slot in page._monitor_slots] == [
        "/camera/0/image_raw",
        "/camera/1/image_raw",
        "/camera/2/image_raw",
        "/camera/3/image_raw",
    ]
    page.close()


def test_recording_page_preflight_reports_missing_configured_topics() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [
            {"name": "/camera/missing/color/image_raw", "type": "sensor_msgs/msg/Image"},
            {"name": "/wx250s/joint_states", "type": "sensor_msgs/msg/JointState"},
        ],
    )
    ctx.discovery.discover = lambda: {  # type: ignore[method-assign]
        "nodes": [],
        "topics": [{"name": "/wx250s/joint_states", "type": "sensor_msgs/msg/JointState"}],
        "services": [],
    }
    page = RecordingPage(ctx)

    errors = page.preflight_recording()

    assert app is not None
    assert any("/camera/missing/color/image_raw" in error for error in errors)
    assert not any("/wx250s/joint_states" in error for error in errors)
    page.close()


def test_recording_page_preflight_falls_back_to_topic_info() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [
            {"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"},
            {"name": "/wx250s/joint_states", "type": "sensor_msgs/msg/JointState"},
        ],
    )
    ctx.discovery.discover = lambda: {  # type: ignore[method-assign]
        "nodes": [],
        "topics": [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
        "services": [],
    }
    ctx.discovery.topic_info = lambda topic: {  # type: ignore[method-assign]
        "name": topic,
        "type": "sensor_msgs/msg/JointState",
        "publisher_count": 1,
        "subscription_count": 0,
    } if topic == "/wx250s/joint_states" else None
    page = RecordingPage(ctx)

    errors = page.preflight_recording()

    assert app is not None
    assert errors == []
    page.close()


def test_recording_page_preflight_requires_joint_state_key() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
    )
    ctx.state.collection_config["dataset"]["requires_robot_obs"] = True
    ctx.state.collection_config["state"]["keys"] = []
    ctx.discovery.discover = lambda: {  # type: ignore[method-assign]
        "nodes": [],
        "topics": [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
        "services": [],
    }
    page = RecordingPage(ctx)

    errors = page.preflight_recording()

    assert app is not None
    assert "configuration has no JointState state key for robot_obs" in errors
    page.close()


def test_recording_page_preflight_allows_camera_only_config() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
    )
    ctx.discovery.discover = lambda: {  # type: ignore[method-assign]
        "nodes": [],
        "topics": [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
        "services": [],
    }
    page = RecordingPage(ctx)

    errors = page.preflight_recording()

    assert app is not None
    assert errors == []
    page.close()


def test_review_page_filters_marks_and_exports_quality_report(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.state.dataset_root = tmp_path
    training = ctx.state.episodes_dir
    training.mkdir(parents=True)
    np.savez_compressed(
        training / "episode_0000000.npz",
        rgb_static=np.full((224, 224, 3), 128, dtype=np.uint8),
        rgb_wrist=np.full((224, 224, 3), 128, dtype=np.uint8),
        robot_obs=np.zeros((6,), dtype=np.float32),
        rel_actions=np.zeros((7,), dtype=np.float32),
        actions=np.zeros((7,), dtype=np.float32),
    )
    np.savez_compressed(
        training / "episode_0000001.npz",
        rgb_static=np.zeros((224, 224, 3), dtype=np.uint8),
        rgb_wrist=np.full((224, 224, 3), 128, dtype=np.uint8),
        robot_obs=np.zeros((6,), dtype=np.float32),
        rel_actions=np.zeros((7,), dtype=np.float32),
        actions=np.zeros((7,), dtype=np.float32),
    )
    page = ReviewPage(ctx)

    page.scan()
    page.status_filter.setCurrentText("warning")
    page.mark_select.setCurrentText("bad")
    page.mark_selected()
    page.export_quality_report()
    report = json.loads((ctx.state.raw_session_dir / "quality_report.json").read_text(encoding="utf-8"))

    assert app is not None
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "episode_0000001.npz"
    assert report["by_status"] == {"ok": 1, "warning": 1, "error": 0}
    assert report["mark_counts"]["bad"] == 1
    assert report["issue_counts"] == {"black_frame:rgb_static": 1}


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
    assert ctx.state.selected_streams == [ctx.last_graph["topics"][1]]


def test_discovery_unchecking_topics_clears_open_config_selected_topic_view() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    discovery = DiscoveryPage(ctx)
    config_page = ConfigPage(ctx)
    ctx.last_graph = {
        "nodes": [],
        "topics": [{"name": "/camera/side/image_raw", "type": "sensor_msgs/msg/Image"}],
        "services": [],
    }
    discovery.populate_graph(ctx.last_graph)

    discovery.topics.item(0, 0).setCheckState(Qt.Checked)
    assert "/camera/side/image_raw" in config_page.selected_topics_view.toPlainText()

    discovery.topics.item(0, 0).setCheckState(Qt.Unchecked)

    assert app is not None
    assert ctx.state.selected_streams == []
    assert config_page.selected_topics_view.toPlainText() == "(none)"


def test_discovery_generate_requires_explicit_checked_topic(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    page = DiscoveryPage(ctx)
    ctx.state.selected_nodes = ["/camera/camera"]
    ctx.last_graph = {
        "nodes": [{"name": "/camera/camera", "type": ""}],
        "topics": [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
        "services": [],
    }
    page.populate_graph(ctx.last_graph)
    warnings = []
    monkeypatch.setattr("robodataset_studio.ui.pages.QMessageBox.warning", lambda *args, **kwargs: warnings.append(args))
    ctx.discovery.node_publishers = lambda node: [{"name": "/should/not/use", "type": "sensor_msgs/msg/Image"}]  # type: ignore[method-assign]

    page.generate_config()

    assert app is not None
    assert warnings
    assert ctx.state.collection_config == {}


def test_discovery_generated_config_refreshes_open_config_page(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    discovery = DiscoveryPage(ctx)
    config_page = ConfigPage(ctx)
    ctx.last_graph = {
        "nodes": [],
        "topics": [
            {"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"},
        ],
        "services": [],
    }
    discovery.populate_graph(ctx.last_graph)
    discovery.topics.item(0, 0).setCheckState(Qt.Checked)
    monkeypatch.setattr("robodataset_studio.ui.pages.QMessageBox.information", lambda *args, **kwargs: None)

    discovery.generate_config()

    assert app is not None
    assert "rgb_static" in config_page.editor.toPlainText()
    assert "/camera/camera/color/image_raw" in config_page.editor.toPlainText()
    assert "/camera/camera/color/image_raw" in config_page.selected_topics_view.toPlainText()
    assert "episode_0000000.npz" in config_page.dataset_preview.toPlainText()
    assert "No config loaded" not in config_page.status.text()


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


def test_settings_ai_values_are_shared_without_yaml_fields(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    settings = SettingsPage(ctx)
    settings.ai_enabled.setCurrentText("enabled")
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_model.setCurrentText("gpt-4.1")
    settings.ai_key.setText("secret-key")
    config_page = ConfigPage(ctx)
    ctx.state.collection_config = ConfigManager().build_default_config(
        ProjectState(),
        [{"name": "/camera/camera/color/image_raw", "type": "sensor_msgs/msg/Image"}],
    )
    config_page.load_context_config()
    captured = {}

    def fake_call(base_url, api_key, payload):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["payload"] = payload
        return config_page.editor.toPlainText()

    monkeypatch.setattr(config_page, "_call_openai_compatible_chat", fake_call)

    config_page.ai_match_config()
    config = ctx.config_manager.loads(config_page.editor.toPlainText())

    assert app is not None
    assert captured["base_url"] == "https://api.example.com/v1"
    assert captured["api_key"] == "secret-key"
    assert captured["payload"]["model"] == "gpt-4.1"
    assert "ai_validation" not in config


def test_settings_are_persisted_to_user_settings_store(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    ctx.settings_store = UserSettingsStore(tmp_path / "settings.json")
    settings = SettingsPage(ctx)
    settings.ai_enabled.setCurrentText("enabled")
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_model.setCurrentText("gpt-4.1")
    settings.ai_key.setText("secret-key")
    settings.language.setCurrentText("English")
    settings.save_ai_settings()

    restored = AppContext()
    restored.settings_store = UserSettingsStore(tmp_path / "settings.json")
    restored.load_user_settings()

    assert app is not None
    assert restored.state.language == "en"
    assert restored.state.ai_enabled is True
    assert restored.state.ai_base_url == "https://api.example.com/v1"
    assert restored.state.ai_model == "gpt-4.1"
    assert restored.state.ai_api_key == "secret-key"


def test_settings_refresh_models_populates_model_combo(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    settings = SettingsPage(ctx)
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_key.setText("secret-key")

    settings.finish_model_refresh(["gpt-b", "gpt-a"], None)

    assert app is not None
    assert [settings.ai_model.itemText(index) for index in range(settings.ai_model.count())] == ["gpt-b", "gpt-a"]
    assert ctx.state.ai_model == "gpt-b"
    assert "2 model" in settings.model_status.text()


def test_settings_refresh_models_reports_empty_list(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    settings = SettingsPage(ctx)
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_key.setText("secret-key")

    settings.finish_model_refresh([], None)

    assert app is not None
    assert settings.model_status.text() == "no available models"


def test_settings_model_dropdown_does_not_start_network_refresh(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    settings = SettingsPage(ctx)
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_key.setText("secret-key")
    settings.ai_model.refresh_callback = lambda: pytest.fail("dropdown should not fetch models")
    settings.ai_model.showPopup()
    settings.ai_model.hidePopup()

    assert app is not None
    assert settings._model_thread is None


def test_settings_refresh_models_starts_background_worker() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    settings = SettingsPage(ctx)
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_key.setText("secret-key")

    settings.refresh_models()

    assert app is not None
    assert settings._model_thread is not None
    assert settings.model_status.text() == "loading models..."
    settings._model_thread.quit()
    settings._model_thread.wait(1000)


def test_settings_close_stops_background_model_worker() -> None:
    app = QApplication.instance() or QApplication([])
    ctx = AppContext()
    settings = SettingsPage(ctx)
    settings.ai_base.setText("https://api.example.com/v1")
    settings.ai_key.setText("secret-key")

    settings.refresh_models()
    settings.close()

    assert app is not None
    assert settings._model_thread is None


def test_main_window_retranslates_navigation_and_tool_windows() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.open_settings()

    settings_window = window._tool_windows[-1]
    settings_page = settings_window.centralWidget()
    settings_page.toggle_language()

    nav_labels = [window.nav.item(index).text() for index in range(window.nav.count())]

    assert app is not None
    assert window.windowTitle() == "RoboDataset Studio"
    assert "Settings" in window._tool_windows_by_title
    assert nav_labels == [
        "1. Config & ROS Topics",
        "2. Recording",
        "3. Data Review",
        "4. Conversion",
        "5. Upload",
    ]
    window.close()


def test_main_window_opens_single_settings_window() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.open_settings()
    first = window._tool_windows[-1]
    window.open_settings()

    assert app is not None
    assert len(window._tool_windows) == 1
    assert window._tool_windows_by_title["Settings"] is first
    assert window._tool_windows[-1] is first
    window.close()


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
