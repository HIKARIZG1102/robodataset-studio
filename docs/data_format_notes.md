# Data Format Notes

更新时间：2026-06-05 01:20 Asia/Shanghai

## 远端数据集位置

确认 `gello_widowx` 数据集主要在 Spaceman_Server：

```text
/data/dataset/calvin/robot_datasets/gello_widowx
```

在 microsate_widowx 上没有找到该精确路径。

## 目录结构

已确认的数据集根结构：

```text
gello_widowx/
  merge_calvin_sessions.py
  raw_sessions/
    <task_name>/
      <version_or_session>/
        training/
          episode_0000000.npz
          lang_annotations/
            auto_lang_ann.npy
  merged_calvin/
    <task_name>/
      <version>/
        merge_manifest.json
        training/
          episode_0000000.npz
          calvin.hdf5
          lang_annotations/
            auto_lang_ann.npy
  hdf5/
    <task_name>/
      ...
```

## 样例任务

已看到的任务目录包括：

- `catch_the_green_cube`
- `catch_the_satellite`
- `catch_the_satellite_2fig`
- `catch_the_satellite_v2`
- `pick_up_the_white_cube`
- `pick_up_the_white_item_then_drop_it_in_the_brown_box`
- `pick_up_white_item`

## 样例规模

`gello_widowx` 根目录大致规模：

- `raw_sessions`: 约 2.1G
- `merged_calvin`: 约 57G
- `hdf5`: 约 140M

样例 `catch_the_satellite_2fig/v1`：

- `merge_manifest.json` 记录 `copy_mode=hardlink`
- `total_sessions=70`
- `total_episodes=7310`
- merged training 下存在连续 `episode_*.npz`
- training 下已有 `calvin.hdf5`

## 合并 / HDF5 转换脚本要点

根目录有：

```text
merge_calvin_sessions.py
```

脚本核心行为：

- 扫描 raw session 的 `training/episode_*.npz`
- 读取 `training/lang_annotations/auto_lang_ann.npy`
- 支持 `hardlink/copy/symlink`
- 写入 `merge_manifest.json`
- 将 CALVIN NPZ episode 转为 `training/calvin.hdf5`
- HDF5 结构包含：
  - `annotations`
  - `episodes/<episode_id>/<npz fields>`
  - 文件 attrs: `format`, `split`, `num_episodes`

## 对当前 PySide6 项目的影响

当前项目应聚焦：

- 监听 ROS2/TCP 数据源，不做机器人控制。
- 写入与现有 CALVIN 数据集兼容的 `episode_*.npz`。
- 保持 `raw_sessions -> merged_calvin -> hdf5` 状态流。
- Review 页面应能扫描 `raw_sessions` 和 `merged_calvin`。
- Convert 页面后续应能复用或兼容 `merge_calvin_sessions.py` 的行为。

