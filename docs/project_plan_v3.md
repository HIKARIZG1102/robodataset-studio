# RoboDataset Studio V3 项目计划书

> 状态：初版整理稿，后续细节可以继续按模块讨论。  
> 目标：在保留 V2 经验的基础上，重做一个以 FastAPI 为本地后端、PySide6 为桌面前端的新版本。

## 1. 背景与定位

V2 版本已经把主要链路跑通，包括 ROS2 topic 发现、配置生成、采集、review、转换、上传、AI 配置辅助等。但随着功能增加，当前 UI 和代码组织出现了几个问题：

- 页面功能过于密集，操作者学习成本高。
- 配置、采集、检查器、review、转换、上传之间的状态关系不够清晰。
- 长耗时任务虽然逐步做了线程化，但整体仍然缺少统一任务管理。
- 配置文件、项目状态、用户设置、采集输出之间的边界还需要更系统。
- 后续需要支持更多机器人、更多相机轨道、更多数据格式扩展，现有页面结构不够适合继续堆功能。

V3 的定位不是在 V2 上继续修补，而是新建一个更清晰的软件工程架构。V2 保留不动，作为参考实现和功能验证来源。

## 2. 总体目标

V3 应该更像常用桌面工具软件：

- 没有打开项目时，只显示顶部菜单和空白工作区。
- 新建项目、打开项目可以使用轻量对话框；配置、采集、review、转换、上传等复杂功能使用可停靠标签页，不使用阻塞式大弹窗。
- 项目打开后，主区域使用类似 VSCode/MATLAB 的标签页组织工作流。
- 检查器是全局右侧栏，随时可拉出查看 ROS topic 和图像监视。
- 一个项目版本对应一个独立项目工作区，同一时间只绑定一份项目级总配置。
- 所有长耗时任务都交给 FastAPI 后端任务系统执行，不阻塞 PySide 前端。
- 所有配置、采集、审查、转换、上传行为都围绕同一份项目配置展开。
- 默认路径使用项目相对路径，方便迁移到其他设备。

## 3. 非目标

V3 初期不追求一次性重写所有 V2 细节：

- 不直接删除或替换 V2。
- 不先做复杂美术化 UI，优先把工具逻辑和交互边界做清楚。
- 不把 FastAPI 做成公网服务，默认只监听本机 `127.0.0.1`。
- 不把 AI API key 写进项目配置或数据集配置。
- 不在第一阶段就实现所有图像滤波算法，只先预留配置结构和预览入口。

## 4. 技术架构

```text
PySide6 Desktop Frontend
  |
  | HTTP / WebSocket
  v
FastAPI Local Backend
  |
  v
Services
  Project / Config / ROS / Inspector / Recording / Review / Convert / Upload / AI / Tasks
```

### 4.1 PySide6 前端职责

- 顶部菜单、轻量对话框、可停靠标签页、右侧检查器等 UI。
- VSCode/MATLAB 风格的可停靠标签页布局。
- 文件夹和文件浏览选择。
- 操作者工作流引导。
- 展示配置表单、YAML、采集计划、review 结果、上传日志。
- 订阅后端任务进度和日志。
- 不直接执行耗时 ROS、转换、上传、AI 请求。

### 4.2 FastAPI 后端职责

- 项目创建、打开、保存、最近项目列表。
- 配置生成、校验、预览、保存、导入导出。
- ROS2 graph 发现、topic info、echo once、hz 检查。
- 图像监视帧获取、裁切/resize 预览。
- 采集 preflight、start、stop、session 输出。
- 本地数据 review、mark 缓存、删除/恢复。
- HDF5 检查、CALVIN layout 检查。
- NPZ session 合并、HDF5 转换。
- SSH/rsync 上传、远端校验、repair/resume。
- AI prompt 生成、模型列表获取、AI 配置匹配、AI 数据 review。
- 统一任务管理和 WebSocket 进度推送。

## 5. 目录规划

当前 V3 项目目录：

```text
robodataset-studio-v3/
  README.md
  RoboDataset-Studio-V3.sh
  pyproject.toml
  requirements.txt
  docs/
    architecture.md
    project_plan_v3.md
  robodataset/
    .gitkeep
  src/robodataset_studio_v3/
    backend/
    frontend/
    models/
    services/
```

计划扩展：

```text
src/robodataset_studio_v3/
  backend/
    main.py
    routers/
      health.py
      projects.py
      config.py
      ros.py
      inspector.py
      recording.py
      review.py
      convert.py
      upload.py
      ai.py
      tasks.py
      settings.py
  frontend/
    main.py
    main_window.py
    api_client.py
    backend_process.py
    dialogs/
      new_project_dialog.py
      open_project_dialog.py
      project_config_dialog.py
      settings_dialog.py
    pages/
      collect_page.py
      review_page.py
      convert_page.py
      upload_page.py
      logs_page.py
    widgets/
      inspector_dock.py
      ros_topic_tree.py
      image_monitor.py
      yaml_editor.py
      task_log_view.py
  models/
    project.py
    config.py
    ros.py
    recording.py
    review.py
    upload.py
    task.py
    settings.py
  services/
    project_service.py
    config_service.py
    ros_service.py
    recording_service.py
    review_service.py
    convert_service.py
    upload_service.py
    ai_service.py
    task_service.py
    settings_service.py
```

## 6. 项目与路径模型

一个项目版本对应一个项目目录：

```text
robodataset/
  projects/
    catch_the_satellite_v1/
      project.yaml
      project_config.yaml
      dataset_config.yaml
      raw_sessions/
      review/
      exports/
      logs/
```

示例项目：

```text
catch_the_satellite_v1
catch_the_satellite_v2
trash_calvin_widowx_v1
test1_depth_v1
```

原则：

- 默认所有项目数据存放在 V3 项目目录下的 `robodataset/projects/`。
- 项目路径默认相对，不写死 `/home/...` 这类机器相关绝对路径。
- 用户可以在配置里显式选择外部磁盘或服务器挂载路径，但这属于用户指定路径，不作为默认。
- `project.yaml` 保存项目身份和轻量元信息。
- `project_config.yaml` 是项目级总配置，保存从采集到上传全流程需要的配置。
- `dataset_config.yaml` 是数据集描述配置，保存将进入 session/数据集内部的可复现数据格式说明。
- 采集开始时，将当前 `dataset_config.yaml` 快照写入 session 根目录，命名为 `collection_config.yaml` 或 `dataset_config.yaml`，保证数据可追溯。
- 一个项目版本最多使用一种项目级总配置；同一份总配置可以被 load 到多个项目中。由于总配置不包含项目名和版本，项目身份始终由 `project.yaml` 管理。如果用户在当前项目版本中 load 另一份总配置，应强制版本号 `+1`，生成新的项目工作区。

## 7. 双配置体系

V3 需要明确区分两套配置文件。

### 7.1 项目级总配置：`project_config.yaml`

用途：

- 作为项目的一站式全流程配置。
- 载入后可以直接完成 ROS 检查、采集、review、转换、上传，不需要每个页面重新设置。
- 覆盖 `dataset_config.yaml` 的全部内容。
- 额外包含各页面运行所需配置，例如服务器地址、上传目标、默认输出目录、review 策略、转换策略、UI 最近选择。

建议内容：

```yaml
dataset_config:
  # 完整嵌入 7.2 中定义的数据集描述配置。
  project: {}
  environment: {}
  instruction: {}
  ros: {}
  robot: {}
  streams: []
  state: {}
  action: {}
  recording: {}
  dataset: {}
  ai_assist: {}

paths:
  project_root: robodataset/projects/<project>_<version>
  raw_sessions: raw_sessions
  review: review
  exports: exports
  logs: logs

collection:
  default_mode: manual
  preflight_required: true
  auto_start_monitor: true
  write_session_config_snapshot: true

review:
  local_checks_enabled: true
  ai_review_enabled: false
  marks_file: review/review_marks.json

convert:
  default_output_dir: exports
  write_hdf5: true
  merge_selected_sessions: true

upload:
  enabled: false
  name: ''
  host: ''
  port: 22
  username: ''
  auth_mode: password_or_key
  password: ''
  remote_root: ''
  use_rsync: true
  repair_resume_enabled: true
  verify_after_upload: true

ros:
  selected_nodes: []
  selected_topics: []
  discovery_snapshot: []

ui_state:
  last_active_tab: Collect
  inspector_visible: true
  inspector_width: 360
```

规则：

- `project_config.yaml` 是操作者主动保存和加载的总配置。
- `project_config.yaml` 不保存项目名称、版本号、operator 等项目身份信息；这些只存在于 `project.yaml`。
- 同一个 `project_config.yaml` 可以导入多个项目，不会因为配置文件里的 project 字段覆盖目标项目身份。
- 总配置中允许保存服务器内网或公网 IP、端口、用户名、远端路径等上传流程信息。
- 密码、API key、token 不直接写入总配置；如果用户坚持保存，应进入本机 settings/keyring，并在总配置里只保留引用名。
- 后端保存前必须校验所有涉及路径、ROS topic、recording、dataset、upload 字段的结构合法性。
- load 总配置时，不从配置中读取或覆盖项目名称和版本。
- load 另一份总配置到当前项目时，版本号必须递增，例如 `v1 -> v2`，避免一个项目版本对应多套配置。

### 7.2 数据集描述配置：`dataset_config.yaml`

用途：

- 描述最终数据集的结构和语义。
- 采集时写入 session 内，作为数据集可复现说明。
- 可由 AI 根据 ROS topic、用户填写信息、默认模板生成。
- 可以从 `project_config.yaml.dataset_config` 提取。

它包含：

- dataset identity snapshot、environment、instruction。dataset identity snapshot 可以从当前项目 `project.yaml` 提取后写入 session 快照，但不作为可移植配置的绑定字段。
- 不包含 ROS 监听选择快照；监听节点/topic 选择属于 `project_config.yaml` 顶层 `ros`。
- robot/state/action。
- streams 和图像预处理。
- recording 采样策略。
- dataset schema 和 metadata extensions。
- AI 生成提示词和返回内容摘要。

规则：

- `dataset_config.yaml` 不包含服务器上传 IP、用户名、远端路径等部署信息。
- `dataset_config.yaml` 不包含本机 UI 状态、最近打开路径、窗口布局。
- `dataset_config.yaml` 不包含被监听的 ROS nodes/topics 列表；它只保留由这些 topic 推导出的 streams/state/action 等数据结构。
- 采集出的每个 session 都保留一份当时的数据集配置快照。
- AI 可以生成完整 `dataset_config.yaml`，也可以生成 patch；覆盖到总配置前必须由用户确认。
- 部分字段从总配置继承，例如 environment、recording、dataset schema。项目名称和版本由当前项目注入到采集 session 快照中。
- 进入数据集内部的配置必须经过清洗，去掉本机绝对路径、密钥、无关 UI 状态。

### 7.3 两套配置的关系

```text
project_config.yaml
  includes dataset_config
  includes collection/review/convert/upload/ui state
  stays in project workspace

dataset_config.yaml
  extracted from project_config.yaml.dataset_config
  saved into session/dataset
  describes data only
```

保存逻辑：

- `Save Project Config`：保存 `project_config.yaml`，并同步生成当前项目根目录下的 `dataset_config.yaml`。
- `Start Recording`：将当前 `dataset_config.yaml` 写入 session 根目录作为快照。
- `Export Dataset Config`：只导出干净的数据集描述配置。
- `Import AI Dataset Config`：只替换或 patch `project_config.yaml.dataset_config`，不修改 upload/settings 等总配置字段。

校验逻辑：

- 总配置校验：检查全流程字段，包括采集、review、转换、上传。
- 数据集配置校验：只检查数据集结构和采集字段。
- session 校验：将实际 episode/HDF5/layout 与 session 内配置快照对比。

## 8. 用户设置与缓存

用户设置不应该进入项目配置，也不应该提交到 Git。

建议位置：

```text
~/.config/robodataset-studio-v3/settings.yaml
~/.config/robodataset-studio-v3/recent_projects.yaml
~/.cache/robodataset-studio-v3/
```

设置内容包括：

- 语言选择。
- 最近打开项目。
- 最近使用的页面和窗口布局。
- AI provider base URL、模型名、是否启用。
- API key 的保存策略。
- 上传信息随总配置保存，不再使用独立服务器 profile。
- 上传默认本地目录和远端目录。
- review 页面最近选择的 session/HDF5/folder。

注意：

- AI key 和服务器密码需要谨慎处理，至少不能写入项目 YAML。
- 如果初期先明文保存在本地设置，需要在 UI 上明确提示。
- 后续可以升级到系统 keyring。

## 9. 顶部菜单设计

没有项目打开时，只有菜单可用：

```text
File
  New Project
  Open Project
  Recent Projects
  Exit

Settings
  Environment
  Server Profiles
  AI Provider
  Language

Help
  Tutorial
  Documentation
  About
```

项目打开后，增加项目相关菜单：

```text
Project
  Project Config
  Import YAML
  Export YAML
  Open Project Folder
  Save Project
  Close Project

Tools
  ROS Discovery
  Toggle Inspector
  Data Review
  Convert
  Upload
```

菜单行为：

- `New Project` 和 `Open Project` 可以是短流程对话框。
- `Project Config`、`ROS Discovery`、`Data Review`、`Convert`、`Upload`、`Logs`、`Tutorial` 等复杂功能打开为工作区标签页。
- 同一类型标签页最多只能打开一个；再次点击菜单时切换到已有标签页，而不是重复创建。
- 标签页支持关闭，必要时提示保存未保存配置。
- 标签页可以拖动到左侧、右侧或主区域，形成类似 VSCode/MATLAB 的分栏布局。
- 全局 Inspector 固定为右侧 dock，可隐藏、显示、调整宽度，但不作为普通工作区标签页重复打开。

## 10. 主界面布局与标签页机制

项目未打开：

```text
Top Menu
-------------------------------------------------
Empty workspace:
  Create or open a project to start.
```

项目打开后：

```text
Top Menu
-------------------------------------------------
Project: catch_the_satellite_v1

[Project Config] [Collect] [Review] [Convert] [Upload] [Logs]

                                      [Inspector]
                                      [Topic Inspector]
                                      [Image Monitor]
```

工作区标签页：

- `Project Config`：项目级总配置和数据集配置编辑。
- `Collect`：加载配置、检查节点、监视图像、开始/停止采集。
- `Review`：episode/HDF5/layout 本地审查和 AI 审查。
- `Convert`：session 合并、NPZ 转 HDF5。
- `Upload`：上传、远端校验、repair/resume。
- `Logs`：统一任务日志、错误信息、历史操作。
- `Tutorial`：打开内置教程页面。

全局右侧栏：

- `Topic Inspector`：通用 topic 检查。
- `Image Monitor`：图像 topic 监视和预处理预览。

标签页规则：

- 每种业务页面使用固定 `tab_id`，例如 `project_config`、`collect`、`review`。
- 如果 tab 已存在，菜单动作只激活它。
- 标签页状态写入本地 settings，下次打开尽量恢复布局。
- 对于运行中的长任务，关闭 tab 不取消任务；任务仍在后端运行，Logs 页可继续查看。
- 对于未保存的配置 tab，关闭前必须提示保存、丢弃或取消关闭。

## 11. 新建项目与打开项目

### 11.1 新建项目对话框

字段：

- Project name。
- Version。
- Operator。
- Notes。

行为：

- 自动生成项目目录名：`<project_name>_<version>`。
- 创建 `project.yaml`。
- 创建默认 `project_config.yaml`。
- 从总配置生成默认 `dataset_config.yaml`。
- 打开项目工作区。

API：

```text
POST /api/projects
GET  /api/projects
GET  /api/projects/{project_id}
POST /api/projects/{project_id}/open
```

### 11.2 打开项目对话框

展示方式：

```text
catch_the_satellite
  v1
  v2

trash_calvin_widowx
  v1
```

要求：

- 项目名和版本分层显示。
- 可搜索。
- 可打开项目目录。
- 可看到最后修改时间、session 数量、是否存在 config。

## 12. Project Config 标签页

Project Config 是项目级配置标签页，不是阻塞式弹窗。它由菜单 `Project -> Project Config` 打开，同一项目内最多存在一个。

建议标签：

```text
[Global]
[Dataset]
[Project]
[Environment]
[ROS Streams]
[Robot]
[Images]
[Recording]
[Review]
[Convert]
[Upload]
[AI Assist]
[YAML]
```

布局原则：

- 表单优先，YAML 可见可编辑。
- `Apply Form -> YAML` 放在表单到 YAML 的方向上。
- `Reload Form <- YAML` 放在 YAML 到表单的方向上。
- `Save` 放在标签页底部。
- `Validate` 可以随时检查当前配置。
- `Save As Template` 后续用于保存通用模板。
- `Global` tab 编辑 `project_config.yaml` 的全流程字段。
- `Dataset` tab 编辑嵌入总配置中的 `dataset_config`。
- `YAML` tab 可在 `project_config.yaml` 和 `dataset_config.yaml` 两种视图之间切换。

底部按钮：

```text
[Validate Global Config] [Validate Dataset Config] [Save Project Config] [Export Dataset Config] [Save As Template]
```

## 13. 数据集描述配置文件

数据集描述配置文件：`dataset_config.yaml`。采集开始时，后端将它作为 session 配置快照写入 session 根目录；为了兼容 V2 和现有 CALVIN 检查逻辑，session 内可同时写出 `collection_config.yaml` 软兼容名称。

建议骨架：

```yaml
project:
  name: ''
  version: ''
  operator: ''
  created_at: ''
  notes: ''

environment:
  type: ''
  workspace: ''
  scene_description: ''
  lighting: ''
  objects: []
  notes: ''

instruction:
  text: ''
  language: ''
  task_family: ''
  success_condition: ''

ros:
  selected_nodes: []
  selected_topics: []
  discovery_snapshot: []

robot:
  name: ''
  model: ''
  description: ''
  joint_state_topic: ''
  joint_count: 0
  joint_order: []
  base_frame: ''
  end_effector_frame: ''
  action_topic: null
  gripper_state_topic: null

streams:
  - name: rgb_wrist
    topic: /camera/camera_wrist/color/image_raw
    message_type: sensor_msgs/msg/Image
    modality: rgb
    role: wrist
    calvin_key: rgb_wrist
    required: true
    dtype: uint8
    shape: [480, 848, 3]
    encoding: rgb8
    preprocessing:
      crop:
        enabled: false
        x: 0
        y: 0
        width: 0
        height: 0
      resize:
        enabled: false
        width: 0
        height: 0
      filters: []

state:
  keys:
    - name: robot_obs
      source_topic: ''
      type: sensor_msgs/msg/JointState
      output_dim: 0
      fields: []
      joint_order: []

action:
  name: rel_actions
  source: derived_from_robot_obs
  source_topic: ''
  source_action_topic: null
  gripper_state_topic: null
  format: delta_state
  dim: 0
  fields: []

recording:
  sample_rate_hz: 10
  stop_mode: duration_sec
  episode_duration_sec: 2.0
  target_samples: 20
  sync_policy: nearest_timestamp
  max_frame_lag_ms: 100
  min_episode_steps: 1
  auto_drop_empty_frames: true
  auto_drop_invalid_actions: true

dataset:
  output_format: [npz, hdf5]
  schema: calvin_style
  split: training
  episode_prefix: episode_
  write_language_annotations: true
  language_annotation_file: lang_annotations/auto_lang_ann.npy
  metadata_extensions:
    - collection_config
    - task_info
    - environment_info
    - robot_info
    - stream_schema

ai_assist:
  config_prompt: ''
  config_response: ''
  review_prompt: ''
  review_response: ''
```

原则：

- 用户没填的字段保持空，不自动写假默认值。
- 勾选的 ROS topic 决定 `streams/state/action` 的候选配置。
- AI 只辅助生成或修改配置，不自动覆盖，必须用户确认。
- 配置应该能准确预览将来生成的数据集结构。
- 配置里的每个采集字段都应在 UI 中有对应可编辑入口，或者明确属于自动探测字段。

## 14. ROS Discovery 与检查器

### 14.1 ROS Discovery

ROS discovery 合并为树状展开列表：

```text
ROS Graph
  /camera
    [ ] /camera/camera/color/image_raw        sensor_msgs/msg/Image
    [ ] /camera/camera/depth/image_rect_raw   sensor_msgs/msg/Image
  /camera_wrist
    [ ] /camera/camera_wrist/color/image_raw  sensor_msgs/msg/Image
  /wx250s
    [ ] /wx250s/joint_states                  sensor_msgs/msg/JointState
```

要求：

- checkbox 选择，不依赖复杂多选。
- topic 名和类型名尽量完整显示。
- 可按 namespace、node 或类型分组。
- 勾选变化后可以生成配置草稿。
- 对勾选 topic 后端可以执行 `topic info`、`echo once`、`hz`，用于辅助填充维度、shape、encoding、字段。

API：

```text
GET  /api/ros/graph
POST /api/ros/topic-info
POST /api/ros/topic-echo-once
POST /api/ros/topic-hz
POST /api/ros/selected
```

### 14.2 全局 Inspector

右侧栏分两个页面：

```text
[Topic Inspector]
[Image Monitor]
```

Topic Inspector：

- 输入或选择 topic。
- 查看 topic info。
- echo once。
- hz 检查。
- 显示消息摘要。
- 显示错误和超时。

Image Monitor：

- 自动根据当前项目配置显示图像 topic。
- 显示 FPS、shape、encoding。
- 显示 mean brightness。
- 支持 crop/resize 预览。
- 后续预留曝光、滤波、亮度提示。

## 15. 图像预处理

V3 的原则：

> 预览看到的结果应该和最终保存到数据集里的结果一致。

图像预处理配置放在每个 stream 下：

```yaml
streams:
  - name: rgb_wrist
    preprocessing:
      crop:
        enabled: true
        x: 10
        y: 20
        width: 640
        height: 480
      resize:
        enabled: true
        width: 224
        height: 224
      filters:
        - type: brightness_hint
        - type: exposure_scale
          alpha: 1.0
          beta: 0
```

初期优先实现：

- crop/resize 配置。
- 采集页实时预览裁切后的画面。
- 数据写入时应用同样的 crop/resize。
- 亮度统计和低亮度 warning。

后续再讨论：

- 客户端侧曝光调整是否应该真的写入数据。
- 相机节点参数调整是否应该通过 ROS parameter service 实现。
- 滤波器是只用于预览，还是用于保存数据。

## 16. Collect 采集页

采集页目标：让操作者明确知道当前会采什么、采多久、输出到哪里。

页面内容：

- 当前项目名和版本。
- 当前加载的 `project_config.yaml` 和由其提取的 `dataset_config.yaml`。
- 数据集结构预览。
- 节点检查按钮。
- 图像监视区域。
- 采集模式。
- start/stop。
- 当前任务日志。

采集模式：

```text
Manual start/stop
Duration based
Sample count based
```

UI 行为：

- Manual 模式不显示 duration/sample 输入。
- Duration 模式显示时长和预计 transition 数。
- Sample count 模式显示目标 sample 数和预计 episode 文件数。
- 旁边小字显示采集频率、输出目录、预计结果。

API：

```text
POST /api/recording/preflight
POST /api/recording/start
POST /api/recording/stop
GET  /api/tasks/{task_id}
WS   /ws/tasks/{task_id}
```

采集输出：

```text
raw_sessions/
  session_YYYYMMDD_HHMMSS/
    collection_config.yaml
    dataset_config.yaml
    training/
      episode_0000000.npz
      episode_0000001.npz
      ...
      lang_annotations/
        auto_lang_ann.npy
    metadata/
      session_summary.json
      stream_schema.json
```

## 17. Review 数据审查

Review 页面分三个顶部子页面：

```text
[Episode Review]
[HDF5 Inspect]
[CALVIN Layout]
```

### 17.1 Episode Review

对象：一个 session 目录。

功能：

- 选择 session root。
- 扫描 `training/episode_*.npz`。
- 展示每条 episode 的字段、shape、dtype、关键数值。
- 和 session 内的 `collection_config.yaml` 对比。
- 本地脚本检查 error/warning。
- 手动标记 good/bad/uncertain。
- 标记状态写入 `review/review_marks.json` 或 session 内 review 文件，下次打开保留。
- 支持删除或移动不想要的数据。
- 支持 AI review。

本地检查至少包括：

- 必需字段缺失：error。
- shape 与配置不一致：error。
- dtype 与配置不一致：warning 或 error，取决于字段。
- 空数组、NaN、Inf：error。
- 图像全黑、全白、亮度过低：warning。
- robot_obs/action 维度不匹配：error。
- 连续样本变化幅度过小：warning。
- language annotation 缺失：warning。
- session config 缺失：warning 或 error。

### 17.2 HDF5 Inspect

对象：一个 HDF5 文件。

功能：

- 选择 HDF5。
- 展开 HDF5 group/dataset 结构。
- 统计总 episode/transition 数。
- 检查核心字段是否存在。
- 检查字段 shape/dtype。
- 输出汇总：总数、有效数、无效数。
- 对每条有问题的数据列出原因。

### 17.3 CALVIN Layout

对象：session、merged dataset 或输出文件夹。

功能：

- 选择 folder。
- 批量检查目录结构。
- 检查 `training/episode_*.npz`。
- 检查 `lang_annotations/auto_lang_ann.npy`。
- 检查 `collection_config.yaml`。
- 检查 HDF5 输出是否存在。
- 输出结构化 summary。

API：

```text
POST /api/review/session/scan
POST /api/review/session/check
POST /api/review/session/mark
POST /api/review/session/delete
POST /api/review/hdf5/check
POST /api/review/layout/check
POST /api/review/ai/prompt
POST /api/review/ai/send
```

## 18. Convert 数据转换

目标：避免按钮功能重复，每个按钮有明确职责。

页面功能：

- 浏览选择 raw sessions 根目录。
- 列出 sessions，checkbox 勾选。
- 选择 output 目录。
- 合并 selected sessions 为 CALVIN-style NPZ 输出。
- 将 selected sessions 转为 HDF5。
- HDF5 输出直接写到用户选择 output 目录，不额外套 training 目录，除非用户显式选择。
- 转换任务后台运行，不阻塞前端。

API：

```text
POST /api/convert/scan
POST /api/convert/merge
POST /api/convert/hdf5
GET  /api/tasks/{task_id}
WS   /ws/tasks/{task_id}
```

## 19. Upload 上传

上传目标：支持大数据集可靠上传。

页面功能：

- 选择本地文件或文件夹。
- browse 本地路径。
- 自动加载当前项目总配置中的 upload 字段。
- 输入远端目录。
- 远端 browse、mkdir。
- 普通上传。
- Repair / Resume verified upload。
- 日志和进度显示。

服务器要求：

- 远端需要可 SSH 登录。
- 推荐有 `rsync`。
- repair/resume 需要远端可执行基本 shell 命令。
- 如果远端缺少命令，应在 UI 中提示，而不是静默失败。
- 远端空间检查属于可选能力，不保证所有服务器都支持。

Manifest 策略：

- manifest 临时生成。
- 不长期保存在本地项目里。
- 不上传到服务器作为数据文件。
- 用于本地和远端文件列表、大小、hash 对比。
- repair/resume 只重传缺失或 hash 不匹配的文件。

推荐 rsync 参数：

```text
--partial --partial-dir=.rsync-partial --append-verify
```

API：

```text
POST /api/upload/connect
POST /api/upload/list
POST /api/upload/mkdir
POST /api/upload/start
POST /api/upload/verify
POST /api/upload/repair
POST /api/upload/space
```

## 20. AI 辅助

AI 设置放在 Settings，不放入项目配置：

- base URL。
- API key。
- model list。
- selected model。
- timeout。
- 是否启用。

### 20.1 AI Config Match

作用：

- 根据当前选择的 ROS nodes/topics 生成或补全 `project_config.yaml.ros`，并同步更新 `dataset_config.yaml` 的 streams/state/action。
- 从 topic info、echo once、hz、图像 shape、JointState 字段等信息推断配置字段。
- 不自动发送，先生成默认 prompt。
- 用户点击发送后才调用 AI。
- AI 返回结果显示在单独预览窗口。
- 用户可以复制字段或点击替换配置。

Prompt 应包含：

- 标准配置模板。
- 用户已填写的 project/environment/instruction/recording/dataset 信息。
- 已选 ROS topic 和 node。
- topic info / echo once / hz 摘要。
- 当前配置 YAML。
- 输出要求：返回完整 YAML 或明确 patch。

### 20.2 AI Review

作用：

- 辅助发现本地脚本难以判断的问题。
- 例如数据变化幅度太小、动作不合理、样本数量不足、图像内容异常、任务描述和数据不匹配。
- 尽量指出具体 episode 编号和原因。

AI review 输入：

- session summary。
- 本地检查结果。
- episode 字段统计。
- 关键数值摘要。
- 可选图像缩略图或亮度/变化统计。
- 当前配置和任务 instruction。

API：

```text
GET  /api/ai/models
POST /api/ai/config-prompt
POST /api/ai/config-match
POST /api/ai/review-prompt
POST /api/ai/review
```

## 21. 任务系统

所有耗时操作都必须走 task manager：

- ROS hz check。
- topic echo once 批量检查。
- 图像监控后台拉流。
- recording。
- review 扫描和检查。
- HDF5 inspect。
- convert。
- upload。
- repair/resume。
- AI 请求。

任务模型：

```yaml
task_id: recording_20260616_120000
kind: recording
status: queued | running | done | failed | cancelled
progress: 0.0
message: ''
logs: []
result: {}
error: ''
created_at: ''
started_at: ''
ended_at: ''
```

API：

```text
POST /api/tasks/{task_id}/cancel
GET  /api/tasks
GET  /api/tasks/{task_id}
WS   /ws/tasks/{task_id}
```

前端要求：

- 任何任务运行时 UI 不冻结。
- 任务可取消。
- 错误显示具体命令、stderr、异常栈摘要。
- Logs 页能看到任务历史。

## 22. FastAPI API 模块草案

```text
/api/health
  GET /api/health

/api/projects
  GET    /api/projects
  POST   /api/projects
  GET    /api/projects/{project_id}
  POST   /api/projects/{project_id}/open
  POST   /api/projects/{project_id}/save

/api/config
  GET    /api/config/{project_id}
  PUT    /api/config/{project_id}
  POST   /api/config/{project_id}/validate
  POST   /api/config/{project_id}/preview
  POST   /api/config/{project_id}/import
  GET    /api/config/{project_id}/export

/api/ros
  GET    /api/ros/graph
  POST   /api/ros/topic-info
  POST   /api/ros/topic-echo-once
  POST   /api/ros/topic-hz

/api/recording
  POST   /api/recording/preflight
  POST   /api/recording/start
  POST   /api/recording/stop

/api/review
  POST   /api/review/session/scan
  POST   /api/review/session/check
  POST   /api/review/session/mark
  POST   /api/review/session/delete
  POST   /api/review/hdf5/check
  POST   /api/review/layout/check

/api/convert
  POST   /api/convert/scan
  POST   /api/convert/merge
  POST   /api/convert/hdf5

/api/upload
  POST   /api/upload/connect
  POST   /api/upload/list
  POST   /api/upload/mkdir
  POST   /api/upload/start
  POST   /api/upload/verify
  POST   /api/upload/repair

/api/ai
  GET    /api/ai/models
  POST   /api/ai/config-prompt
  POST   /api/ai/config-match
  POST   /api/ai/review-prompt
  POST   /api/ai/review

/api/settings
  GET    /api/settings
  PUT    /api/settings
```

## 23. 数据集格式原则

V3 仍以 CALVIN-style NPZ/HDF5 为基础，但要支持扩展。

核心字段：

- RGB streams：`rgb_static`、`rgb_wrist`、`rgb_1` 等可扩展命名。
- State：`robot_obs` 或配置指定的 state keys。
- Action：`rel_actions`、`actions`。
- Language annotation：`lang_annotations/auto_lang_ann.npy`。
- Config snapshot：`dataset_config.yaml`，并为兼容旧检查逻辑可同时写出 `collection_config.yaml`。

扩展字段：

- environment metadata。
- robot metadata。
- stream schema。
- task information。
- preprocessing record。
- review marks。

原则：

- 训练脚本需要的核心键保持兼容。
- 扩展信息不破坏核心 CALVIN 读取逻辑。
- 数据结构预览必须由当前配置实时生成。
- 如果配置增加 stream 或 state 维度，采集、review、convert 都应基于配置泛化检查。

## 24. V2 到 V3 的迁移

迁移策略：

- V2 不动。
- V3 可以手动导入 V2 的 YAML。
- V3 可以读取 V2 采集出的 session 进行 review/convert。
- V3 初期不自动批量迁移所有旧配置，避免误改。
- V3 必须完整覆盖 V2 已经跑通的按键功能；UI 可以重新组织，但功能不能丢。

可复用逻辑：

- YAML 配置生成经验。
- ROS topic 探测逻辑。
- 采集同步逻辑。
- CALVIN NPZ/HDF5 检查逻辑。
- merge/convert 脚本能力。
- 上传 repair/resume 经验。

需要重构的部分：

- UI 状态管理。
- 长任务管理。
- 项目路径和缓存策略。
- 配置和表单同步。
- review 结果结构化。

## 25. V2 功能还原测试清单

下面清单用于确认 V3 是否还原 V2 必要功能。实现并通过手工或自动测试后，将对应条目标记为完成。标注为“基础 hook”的项目表示前后端入口和任务记录已经接通，但仍需要继续接入 V2 已验证的生产逻辑。

### 25.1 项目与配置

- [x] `New Project`：创建新项目版本目录，生成 `project.yaml`、`project_config.yaml`、`dataset_config.yaml`。
- [x] `Open Project`：按项目名和版本打开已有项目。
- [x] `Project Config`：打开单实例配置标签页。
- [ ] `Apply Form -> YAML`：将表单内容写入当前 YAML 视图。
- [ ] `Reload Form <- YAML`：从 YAML 回填表单。
- [ ] `Validate Global Config`：校验总配置，包括采集、review、转换、上传字段。
- [ ] `Validate Dataset Config`：校验数据集描述配置。
- [x] `Save Project Config`：保存总配置，并同步生成数据集配置。
- [ ] `Export Dataset Config`：导出干净的数据集描述配置。
- [ ] `Import YAML`：导入 V2/V3 YAML 并按规则创建或升级项目版本。
- [x] `Dataset Structure Preview`：根据当前配置实时预览未来数据集结构。

### 25.2 ROS Discovery 与 Inspector

- [ ] `ROS Discovery`：展开式 ROS graph/topic tree。（基础 ROS graph API 已完成）
- [ ] `Topic Checkbox Selection`：勾选 topic 后写入配置草稿。
- [x] `Topic Info`：查询选中 topic 类型、publisher/subscriber。
- [x] `Echo Once`：对选中 topic 获取一次消息摘要。
- [x] `Hz Check`：检查 topic 发布频率。
- [ ] `Image Monitor`：按配置显示图像 topic 实时画面。
- [ ] `Image Stats`：显示 FPS、shape、encoding、亮度。
- [ ] `Crop/Resize Preview`：显示裁切和 resize 后的实际保存效果。

### 25.3 AI 配置辅助

- [x] `Default Prompt`：根据标准模板、用户填写信息、选中 ROS topic、topic info/echo/hz 生成 prompt。
- [ ] `Send AI Config Match`：手动发送 prompt，不自动发送。（基础 AI send hook 已完成）
- [ ] `AI Config Preview`：单独显示 AI 返回的 YAML/patch。
- [ ] `Apply AI Result`：用户确认后将 AI 结果写入 `dataset_config`。
- [ ] `AI Settings`：保存 base URL、model、timeout 等本地设置，密钥不进入项目配置。
- [ ] `Model List`：根据 base URL 和 key 拉取可用模型列表。（基础 hook 已完成，真实 provider 通信待接入）

### 25.4 采集

- [x] `Load Project Config`：采集页从项目总配置刷新采集计划。
- [x] `Preflight Check`：非阻塞检查 topic 是否存在、echo once、hz。
- [ ] `Manual Recording`：手动开始/停止采集。（基础 start/stop task 和 session snapshot 已完成，真实 ROS 写帧待接入）
- [ ] `Duration Recording`：按时长采集并显示预计 transition 数。
- [ ] `Sample Count Recording`：按样本数采集并显示预计 episode 文件数。
- [ ] `Start Recording`：后台任务采集，不冻结前端。（基础 task 已完成，真实采集待接入）
- [ ] `Stop Recording`：正常终止后台采集任务，不误报 crash。（基础 task 已完成）
- [x] `Session Config Snapshot`：每个 session 写入 `dataset_config.yaml` 和兼容 `collection_config.yaml`。
- [ ] `CALVIN NPZ Output`：写出 `training/episode_*.npz`。
- [ ] `Language Annotation`：写出 `lang_annotations/auto_lang_ann.npy`。
- [ ] `Preprocessing Save`：保存图像与预览裁切/resize 一致。

### 25.5 Review

- [x] `Episode Review Scan`：选择 session 并扫描 episode。
- [ ] `Episode Detail`：显示字段、shape、dtype、关键数值。（基础 npz 检查服务已完成，详细 UI 待完善）
- [ ] `Local Check`：按配置检查缺失字段、shape、dtype、NaN/Inf、亮度、维度等。（基础检查已完成，配置对齐检查待完善）
- [x] `Review Summary`：显示总数、有效数、无效数、warning/error 数。
- [x] `Manual Mark`：支持 good/bad/uncertain。
- [x] `Mark Persistence`：重启后保留 mark 状态。
- [ ] `Delete/Move Bad Episode`：删除或移动不需要的数据。
- [x] `HDF5 Inspect`：选择 HDF5 并检查结构、字段、episode 数。
- [ ] `HDF5 Check Summary`：列出总数、有效数、无效数和逐条原因。（基础结构检查已完成）
- [x] `CALVIN Layout Check`：选择 session/dataset/folder 并批量检查布局。
- [x] `AI Review Prompt`：生成数据质量审查 prompt。
- [ ] `AI Review Result`：显示 AI 指出的可疑 episode 和原因。

### 25.6 Convert

- [x] `Browse Raw Root`：选择 raw sessions 根目录。
- [x] `Scan Sessions`：列出可合并 session。
- [ ] `Select Sessions`：checkbox 选择要处理的 sessions。
- [ ] `Browse Output`：选择输出目录。
- [ ] `Merge Sessions`：将勾选 sessions 合并为 CALVIN-style NPZ。（基础 task hook 已完成，V2 merge 逻辑待接入）
- [ ] `Convert Selected To HDF5`：将勾选 sessions 直接转换为 HDF5。（基础 task hook 已完成，V2 converter 待接入）
- [x] `Background Convert Task`：转换不阻塞前端。
- [x] `Convert Log`：显示输出路径、计数、错误原因。

### 25.7 Upload

- [x] `Server Profile`：配置服务器 host、port、username、remote root。
- [x] `Browse Local File`：选择单个本地文件上传。
- [x] `Browse Local Folder`：选择本地文件夹上传。
- [ ] `Remote Browse`：浏览远端目录。
- [ ] `Remote Mkdir`：创建远端目录。
- [ ] `Upload`：普通上传。（基础 dependency/task hook 已完成；upload 信息随总配置自动加载）
- [ ] `Verify Remote`：校验远端文件是否完整。（基础 hook 已完成）
- [ ] `Repair / Resume Verified Upload`：只重传缺失或 hash 不匹配文件。（基础 hook 已完成，真实 rsync 参数待接入）
- [ ] `Temporary Manifest`：manifest 临时生成，不作为数据上传或长期堆积。（设计已明确，真实 manifest 流程待接入）
- [x] `Upload Background Task`：上传、校验、repair 不阻塞前端。
- [x] `Dependency Warning`：服务器缺少 ssh/rsync/shell 命令时明确提示。

### 25.8 通用行为

- [x] `Single Instance Tabs`：同一类型标签页最多打开一个。
- [ ] `Dockable Tabs`：标签页可拖动到左侧、右侧或主区域。
- [x] `Inspector Dock`：右侧 Inspector 可隐藏/显示/调整宽度。
- [x] `Settings Persistence`：语言、AI、服务器、最近路径、窗口布局重启后保留。
- [x] `Task Cancel`：长任务可取消。
- [x] `Logs Page`：集中查看任务历史、stdout/stderr、错误摘要。
- [x] `Tutorial`：Help 菜单可打开完整操作教程。

## 26. 实施阶段

### Phase 1：V3 Shell

- FastAPI skeleton。
- PySide shell。
- 后端自动启动。
- New/Open Project。
- 项目目录结构。
- 顶部菜单和空工作区。
- 右侧 inspector 占位。

### Phase 2：Project Config

- Project Config 标签页。
- `project_config.yaml` 和 `dataset_config.yaml` schema。
- 表单/YAML 双向同步。
- 配置校验。
- 数据集结构预览。
- 保存到项目 workspace。

### Phase 3：ROS Discovery / Inspector

- ROS graph tree。
- checkbox 选择。
- topic info / echo once / hz。
- inspector 右侧栏。
- Image Monitor 基础预览。

### Phase 4：Collect

- 节点 preflight。
- 采集计划预览。
- Manual / Duration / Sample count。
- 后台 recording task。
- session config snapshot。
- crop/resize 保存一致性。

### Phase 5：Review

- Episode Review。
- HDF5 Inspect。
- CALVIN Layout。
- mark 缓存。
- 本地脚本检查。
- AI review prompt 和结果窗口。

### Phase 6：Convert

- session scan。
- selected sessions merge。
- selected sessions HDF5。
- 后台转换任务。
- 输出路径清晰化。

### Phase 7：Upload

- upload 信息完全来自总配置的 `upload` 段。
- 本地文件/文件夹 browse。
- 远端 browse/mkdir。
- 普通上传。
- repair/resume verified upload。
- 临时 manifest。

### Phase 8：Polish

- Tutorial。
- README。
- 错误提示统一化。
- Logs 页。
- 设置持久化。
- 打包和桌面启动。

## 27. 风险与待讨论问题

需要继续讨论：

- 项目版本创建后是否允许修改版本号。（可以修改，但是如果存在修改后相同的版本号与项目名称，则弹出警告禁止修改）
- upload 不允许独立 profile；严格跟随总配置。一个项目 load 一个总配置后，Upload 页面自动使用该配置中的 upload 字段。
- 图像滤波是否写入保存数据，还是只做 preview。（先不写入）
- AI key 是否明文保存到本地 settings，还是要求每次输入或使用 keyring。（保存）
- HDF5 输出按 session、按项目、还是按 export job 管理。（？没看懂）
- review mark 放在 session 内还是项目 review 目录中。（放在review目录中）
- 上传远端空间检查是否保留为可选按钮，还是完全放入上传前自动检查。（手动检查）
- FastAPI 是否需要支持 LAN 访问，还是仅本机。（先仅本机）
- ROS2 环境 setup 是由启动脚本负责，还是后端支持配置多个 ROS workspace。（ros2节点的建立由我们在外部执行；如果你需要在内部跑ros2 topic之类的检测你自己后端加workspace）

## 28. 下一步建议

建议下一步先实现 Phase 2 的 Project Config，因为它会决定后面采集、review、convert 的数据契约。

具体顺序：

1. 固化 `project_config.yaml` 与 `dataset_config.yaml` schema。
2. 做 Project Config 标签页和 YAML editor。
3. 做配置预览 API，保证每次配置变化都能看到未来数据集结构。
4. 做 ROS Discovery tree，将勾选 topic 写入配置草稿。
5. 接上 Topic Inspector 的 topic info / echo once / hz。

这个顺序能先把 V3 的核心状态模型定住，后续采集和 review 才不会继续变成页面之间各自维护状态。
