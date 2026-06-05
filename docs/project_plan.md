# ROS2 机器人数据采集平台项目计划书

> 目标：设计一个运行在 Ubuntu / ROS2 环境中的前后端一体可执行程序，用于发现 ROS2 / TCP 数据源，配置机器人与场景元数据，采集并清洗多模态数据，转换为 NPZ / HDF5 数据集，最后上传到 Hugging Face Hub 或指定 SSH 服务器目录。

本文是项目建设讨论稿，偏工程规划与需求拆解。它不是网页端方案，而是一个本地桌面可执行程序方案。

---

## 1. 项目定位

### 1.1 核心问题

当前物理机采集数据依赖较多脚本、终端命令和人工检查，典型流程包括：

- 启动 ROS2 / RealSense / WidowX / OpenVLA / PI05 节点。
- 手动确认 topic、节点、相机流、joint state、action topic 是否正常。
- 手动配置采集参数、instruction、机器人描述、相机名称、关节字段。
- 采集 NPZ 文件。
- 筛查空帧、坏帧、异常轨迹。
- 合并成 CALVIN 风格目录或 HDF5。
- 上传到服务器或 HF 仓库。

这个项目要把上述过程整合为一个可视化、本地运行、可追踪的数据采集平台。

### 1.2 目标用户

- 机器人数据采集人员。
- VLA / imitation learning / robot foundation model 训练人员。
- 同时使用物理机器人与 Genesis 仿真平台的研究人员。
- 需要把原始 ROS2 数据变成 NPZ / HDF5 / Hugging Face dataset 的工程人员。

### 1.3 运行环境

主要运行环境：

- Ubuntu 22.04 / 24.04。
- ROS2 Humble / Jazzy，首期建议优先支持 Humble。
- Python 3.10+。
- 可选 GPU，用于图像质量检测、AI 辅助校验、预览加速。

不作为首期重点：

- Windows 原生运行。
- 浏览器网页部署。
- 云端多用户协同平台。

---

## 2. 产品形态

### 2.1 推荐形态

推荐做成一个 **本地桌面可执行程序**：

- 前端：桌面 UI。
- 后端：本地 Python 服务 / 进程。
- ROS2：通过本地 Python ROS2 client 或命令行桥接。
- 数据处理：Python pipeline。
- 打包：Ubuntu AppImage / deb 包 / Python wheel + launcher。

### 2.2 可选技术路线

#### 方案 A：Tauri + Python 后端

优点：

- 桌面程序体积小。
- UI 体验好。
- 前端可用 React / Vue / Svelte。
- 后端 Python 适合 ROS2、HDF5、NumPy、OpenCV、Hugging Face。

缺点：

- Rust / Tauri 与 Python 后端通信需要设计。
- 打包时要处理 Python 环境、ROS2 环境和系统依赖。

推荐程度：高。

#### 方案 B：PySide6 / Qt for Python

优点：

- 全 Python 栈，和 ROS2 / h5py / NumPy 结合自然。
- 打包链路相对简单。
- 对本地工具类应用很稳。

缺点：

- UI 现代感和前端生态弱于 Tauri / Electron。
- 复杂界面开发效率可能稍低。

推荐程度：高，尤其适合首版 MVP。

#### 方案 C：Electron + Python 后端

优点：

- UI 开发最熟悉，生态成熟。
- 日志窗口、配置编辑器、数据预览都好做。

缺点：

- 程序体积大。
- 在机器人工作站上资源占用更高。

推荐程度：中。

### 2.3 建议路线

首版建议：

```text
PySide6 / Qt for Python + Python 后端一体化
```

理由：

- 当前核心难点不在炫酷 UI，而在 ROS2 数据发现、采集稳定性、HDF5 转换和校验。
- Python 原生接入 `rclpy`、`h5py`、`numpy`、`opencv-python`、`huggingface_hub` 更直接。
- 后续如果 UI 复杂度上升，可以保留 Python 后端，替换为 Tauri 前端。

### 2.4 PySide6 内存与稳定性注意事项

PySide6 适合首版快速落地，但它也更容易在长期运行的数据采集场景中暴露内存、线程和对象生命周期问题。这个项目涉及多相机图像预览、ROS2 topic 订阅、终端子进程、日志窗口和大文件转换，因此必须从架构上避免把所有逻辑塞进 UI 对象。

推荐原则：

```text
PySide6 UI 只做控制台和可视化
核心采集 / 转换 / 上传逻辑放到独立 Python service 或子进程
```

建议架构：

```text
PySide6 UI
  -> local API / IPC
Python Core Service
  -> ROS2 recorder process
  -> converter process
  -> uploader process
```

重点注意事项：

- 不要在 Qt 主线程里运行 `rclpy.spin()`。ROS2 listener 应该在独立线程或独立进程中运行，UI 只接收降频后的状态和预览帧。
- 图像预览必须限帧。RealSense / 多相机可以 30 FPS 采集，但 UI 预览建议限制到 5-10 FPS。
- 不要每帧都长期保存 `QImage` / `QPixmap`。缩略图、预览帧、AI 检测帧都要使用 LRU cache 或固定大小 ring buffer。
- 日志窗口不能无限 append。`QPlainTextEdit` / terminal output 应限制最大行数，Inspector 每个终端面板最多保留 2000 行，完整日志后续写入文件。
- 页面关闭、topic preview 关闭、采集停止时，必须断开 signal/slot，停止 worker，释放 subscriber。
- `QThread` 必须完整退出，推荐顺序：

```python
worker.stop()
thread.quit()
thread.wait()
worker.deleteLater()
thread.deleteLater()
```

- recorder、converter、uploader 这类长任务优先用独立子进程。UI 崩溃时，不应轻易损坏正在写入的数据。
- 所有由 UI 打开的 terminal、topic echo、topic hz、image viewer 都要注册到 `Process Display` 页面，由统一进程管理器负责安全退出。
- 大数组不要直接跨 Qt signal 频繁传递。图像帧可以传共享内存引用、文件路径、压缩 JPEG bytes，或只传降采样 preview。
- HDF5 转换、NPZ 合并、AI 检测不要阻塞 UI。长任务必须有进度、取消、失败恢复和日志文件。
- 定期做内存压测：模拟多相机预览 + topic echo + 采集 2 小时，观察 RSS 是否稳定。

PySide6 / Tauri / Electron 选型补充：

| 方案                   | 优点                                                  | 风险                                             | 建议                         |
| ---------------------- | ----------------------------------------------------- | ------------------------------------------------ | ---------------------------- |
| PySide6                | Python 全栈，接 ROS2 / h5py / OpenCV 最直接，MVP 最快 | 图像预览、线程、signal、QPixmap 容易产生内存问题 | 适合首版，但核心任务要进程化 |
| Tauri + Python 后端    | UI 现代，资源占用比 Electron 低，前后端边界清楚       | IPC、打包、Python 后端管理更复杂                 | 适合中长期演进               |
| Electron + Python 后端 | Web UI 生态成熟，复杂界面开发舒服                     | 内存占用高，不适合采集机长期重负载运行           | 团队非常熟 Electron 时再考虑 |

结论：首版可以选 PySide6，但必须从第一天就把 `recorder / converter / uploader / ROS2 listener` 做成可独立停止和监控的后台任务。这样未来如果 UI 换成 Tauri，核心采集逻辑也可以复用。

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────┐
│ Desktop UI                                    │
│ - 四个主工作区，而不是把所有工具平铺成同级导航  │
│ - 配置与 ROS Topic                             │
│ - 采集                                         │
│ - 数据转换                                     │
│ - 上传                                         │
│ - 角落工具：Process Display / Settings         │
└───────────────────┬──────────────────────────┘
                    │ local IPC / direct call
┌───────────────────▼──────────────────────────┐
│ Application Core                              │
│ - Project Manager                             │
│ - Config Manager                              │
│ - ROS2 Discovery Service                      │
│ - TCP Listener Service                        │
│ - Recorder Service                            │
│ - Dataset Validator                           │
│ - NPZ / HDF5 Converter                        │
│ - Upload Manager                              │
│ - AI Assistant Adapter                        │
└───────────────────┬──────────────────────────┘
                    │
┌───────────────────▼──────────────────────────┐
│ External Systems                              │
│ - ROS2 graph / topics / services              │
│ - Physical robot nodes                         │
│ - Genesis simulation ROS2 bridge               │
│ - Local filesystem                             │
│ - Hugging Face Hub                             │
│ - SSH / SFTP server                            │
│ - OpenAI-compatible LLM / VLM APIs             │
└──────────────────────────────────────────────┘
```

---

## 3.1 UI 页面组织

这个程序不应该把节点发现、topic 监听、YAML 编辑、采集、预览、转换、上传都挤在一个页面里，也不应该把十几个功能页面都平铺成同级导航。更合理的形态是一个以采集流程为主线的四段式工作台：左侧只显示高频主工作区，右侧在当前工作区内用 tabs / stepper 展开细节。

推荐主导航：

```text
RoboDataset Studio
├── 1. 配置与 ROS Topic
├── 2. 采集
├── 3. 数据转换
├── 4. 上传
└── 角落工具
    ├── Process
    └── Settings
```

主工作区与原有功能对应关系：

```text
1. 配置与 ROS Topic
   ├── Project
   ├── Environment
   ├── Discovery
   ├── Inspector
   └── Config

2. 采集
   ├── Recording
   └── Review

3. 数据转换
   └── Convert

4. 上传
   └── Upload

角落工具
   ├── Process
   └── Settings
```

原则：

- 保留原有所有功能页面和后端能力，但不再把它们暴露成同级主导航。
- 主导航只承载用户心智里的四个阶段：先配置并选择 ROS topic，再采集，再转换，再上传。
- Project、Environment、Discovery、Inspector、Config 是“配置与 ROS Topic”工作区内的子步骤。
- Recording 和 Review 是“采集”工作区内的子步骤，Review 仍然可以检查单个 NPZ、CALVIN layout 和 HDF5 概览。
- Process Display 与 Settings 不参与主流程。它们应该放在窗口角落或侧栏底部，作为低频工具入口。
- API key、AI provider、上传认证、默认路径等敏感或全局设置只放在 Settings 内，不在主流程中反复暴露。

### 3.1.1 配置与 ROS Topic 工作区

用途：完成项目选择、运行环境检查、ROS2 / TCP 数据源发现、topic 深入检查，以及采集 YAML 生成。

这个工作区包含原有 Project、Environment、Discovery、Inspector、Config 五个子页面。它们可以用顶部 tabs、左侧二级步骤条或折叠面板组织，但在用户心智上属于同一个“配置”阶段。

推荐子步骤：

```text
配置与 ROS Topic
├── Project
├── Environment
├── Discovery
├── Inspector
└── Config
```

#### Project 子页面

用途：管理采集项目和数据集版本。

内容：

- 新建项目。
- 打开已有项目。
- task name。
- version。
- dataset root。
- 当前 session。
- 最近项目列表。
- 项目级 metadata。

#### Environment 子页面

用途：检查 ROS2 / Ubuntu / 机器人运行环境。

内容：

- Ubuntu 版本。
- ROS2 distro。
- ROS_DOMAIN_ID。
- RMW_IMPLEMENTATION。
- 已 source 的 workspace。
- Python / conda 环境。
- GPU / camera / USB 设备粗略检测。
- Genesis 是否可用。
- 环境检查报告。

#### Discovery 子页面

用途：发现当前 ROS2 graph 和 TCP 数据源。

内容：

- ROS2 node list。
- topic list。
- service list。
- topic type。
- topic hz。
- TCP endpoint probe。
- 节点选择。

#### Inspector 子页面

用途：深入查看某个 node/topic/stream。

内容：

- 从 Discovery 已发现的 node/topic 中选择，也允许手动输入临时 topic。
- topic echo。
- topic hz。
- node info。
- node info、topic echo、topic hz、preview log 必须分开显示为独立终端式面板，实时滚动，不混在同一个输出框。
- 每个 Start 操作必须有对应 Stop 操作。
- Stop 后需要安全退出对应 ROS2 CLI / worker，不残留多余进程。
- `sensor_msgs/msg/Image` 实时 image viewer，预览显示必须来自当前真实 ROS image topic 最新帧。
- 预览 buffer 必须采用 latest-frame single-slot 策略：订阅线程只保留最新帧，UI 定时器主动拉取并显示最新帧，不按帧发送 Qt signal，不排队积压大图。
- ROS image callback 不应做昂贵的 RGB/depth 转换；回调只保存最新 raw bytes 和 metadata，UI display timer 在需要显示时转换最新帧。
- 停止预览或关闭页面时必须清空 worker latest frame、UI latest frame、paused frame 和显示 pixmap。
- 图像显示面板应使用自绘 `paintEvent` 或等价机制绘制最新 `QImage`，不要依赖 `QLabel.setPixmap()` 作为高频视频刷新核心。
- Stop / close 时应先停止 worker，再断开 worker 到 UI 的 signal，避免关闭窗口后异步 signal 访问已销毁控件。
- Display 应自动适配 ROS image message 的 width、height、encoding、step 和实际接收 FPS，并在侧栏显示这些真实检测到的特征。
- 每次启动 image preview 应创建唯一 ROS preview node 名称，避免旧订阅节点残留导致用户误判当前预览状态。
- Preview Log 应实时显示实际收到的 frame 计数、encoding 和 size，便于确认显示的是当前真实相机流。
- 预览应支持播放 FPS 设置，并根据已观测到的相机 ROS topic 最大接收 FPS 自动抬高最小播放 FPS。
- 预览应支持暂停；暂停后冻结当前真实帧，允许用户查看静态图。
- 暂停时显示基于当前真实帧像素计算的亮度 / 欠曝 / 过曝 / RGB 均值 / 3x3 亮度分布。除非 ROS topic 或相机 metadata 明确提供，不允许伪造曝光时间、白平衡增益等相机参数。
- 图像预览只能默认列出 `sensor_msgs/msg/Image` topic，避免误选 `/parameter_events` 这类非图像 topic。
- 常见图像 encoding 预览：`rgb8`、`bgr8`、`rgba8`、`bgra8`、`mono8`、`mono16`。
- 深度图像应支持 `16UC1` / `32FC1` 等 encoding 的归一化灰度显示，后续可升级为伪彩色。
- 鼠标采样图像坐标和 RGB 值。
- depth viewer。
- lidar/event/tactile renderer。
- logs。
- 单独弹出的终端预览窗口。

#### Config 子页面

用途：生成和编辑采集 YAML。

内容：

- 自动生成配置。
- 表单编辑。
- YAML 原文编辑。
- schema 校验。
- AI 辅助校验。
- 模板保存 / 加载。

### 3.1.2 采集工作区

用途：启动监听式采集、查看 episode 状态、进行数据预览和坏样本筛查。

这个工作区包含原有 Recording 和 Review 两个子页面。

推荐子步骤：

```text
采集
├── Recording
└── Review
```

#### Recording 子页面

用途：正式采集数据。

内容：

- 开始 / 暂停 / 停止。
- 当前 episode 状态。
- 实时帧率。
- topic 延迟。
- 数据缓存大小。
- 采集日志。
- 成功 / 失败标记。
- 删除当前 episode。

#### Review 子页面

用途：数据预览、筛查、删除坏样本。

内容：

- episode 列表。
- 多模态帧预览。
- 图像 / 深度 / lidar / event camera 可视化。
- action / gripper / joint 曲线。
- AI 坏帧建议。
- 手动删除。
- 质量报告。

### 3.1.3 数据转换工作区

用途：合并 NPZ、转换 HDF5、生成 metadata。

内容：

- dry-run 合并计划。
- NPZ 字段检查。
- HDF5 schema 选择。
- 转换进度。
- 转换后校验。
- HDF5 stats 预览。

### 3.1.4 上传工作区

用途：发布数据集。

内容：

- Hugging Face token / repo。
- SSH / SFTP 服务器。
- 远端目录浏览。
- 上传 manifest。
- 上传进度。
- hash 校验。
- dataset card 生成。

### 3.1.5 Process 角落工具

用途：管理所有由程序启动的后台进程。

内容：

- terminal。
- topic echo。
- topic hz。
- image viewer。
- recorder。
- converter。
- uploader。
- 一键安全停止。

### 3.1.6 Settings 角落工具

用途：全局设置。

内容：

- AI provider。
- API key。
- 默认路径。
- 默认 ROS 环境。
- UI 主题。
- 上传认证。
- 模板管理。

### 3.1.7 页面间状态流

页面之间应该有明确状态流，而不是互相散乱读写：

```text
配置与 ROS Topic
  Project -> Environment -> Discovery -> Inspector -> Config
    -> 采集
      Recording -> Review
        -> 数据转换
          Convert
            -> 上传
              Upload
```

跨页面共享状态：

```yaml
active_project:
  task_name:
  version:
  dataset_root:
  selected_nodes:
  selected_streams:
  collection_config:
  current_session:
  review_marks:
  conversion_outputs:
  upload_targets:
```

允许用户跳转页面，但在关键步骤前做检查：

- 没有 project，不允许 recording。
- 没有 config，不允许 recording。
- 没有 raw data，不允许 convert。
- 没有 converted dataset，不允许 upload。

---

## 4. 核心功能规划

## 4.1 功能一：配置与 ROS2 节点发现

### 4.1.1 节点发现

程序启动后自动检测：

- 当前 ROS_DOMAIN_ID。
- 当前 RMW_IMPLEMENTATION。
- 可用 ROS2 节点。
- 每个节点发布 / 订阅的 topic。
- topic 类型。
- topic 频率估计。
- topic 消息大小估计。
- 是否有图像流、关节状态、动作指令、tf、相机 info。

建议调用方式：

- `rclpy` graph API。
- 必要时调用：
  - `ros2 node list`
  - `ros2 node info`
  - `ros2 topic list -t`
  - `ros2 topic hz`
  - `ros2 topic echo --once`

### 4.1.2 节点详情面板

用户点击某个节点后显示：

- 节点名称。
- namespace。
- publishers。
- subscribers。
- services。
- parameters。
- 最近日志。
- topic 实时消息预览。

其中 `topic 实时消息预览` 不应该只是一次性的 `ros2 topic echo --once`。用户点击预览后，可以打开一个独立的终端/预览窗口，持续显示该 topic 的数据流、频率、最近消息和错误信息。这个窗口关闭时，程序必须安全停止对应的子进程或 ROS2 subscription，避免后台残留 `ros2 topic echo`、`ros2 topic hz`、图像订阅器等进程。

### 4.1.3 运行进程管理面板

由于用户会频繁打开日志、topic echo、topic hz、图像预览、采集进程、转换进程和上传进程，程序需要内置一个 `Process Display` 页面，用来管理当前仍在运行的子进程。

该页面建议显示：

- 进程类型：terminal / topic_echo / topic_hz / image_viewer / recorder / converter / uploader。
- PID。
- 启动命令。
- 启动时间。
- 已运行时长。
- 当前状态：running / stopping / exited / failed。
- stdout / stderr 最近日志。
- CPU / memory 粗略占用。
- 所属 UI 页面或任务。

用户可以：

- 打开进程日志。
- 停止单个进程。
- 停止某个任务组的所有进程。
- 清理已退出进程记录。
- 在关闭程序前一键安全停止所有后台进程。

安全退出策略：

1. 优先向子进程发送 `SIGINT`，模拟用户 Ctrl-C，让 ROS2 节点有机会释放资源。
2. 超时未退出时发送 `SIGTERM`。
3. 再超时才允许用户选择 `SIGKILL`。
4. 对 recorder / converter / uploader 这类写文件任务，默认不直接 kill，先提示可能损坏数据。
5. 每个进程都归属到一个 `process_group_id`，关闭窗口时只关闭该窗口创建的子进程，不误杀用户手动启动的 ROS2 核心节点。

进程记录示例：

```json
{
  "process_id": "proc_topic_echo_0007",
  "pid": 38219,
  "type": "topic_echo",
  "command": "ros2 topic echo /wx250s/joint_states",
  "status": "running",
  "started_at": "2026-06-04T15:30:00+08:00",
  "owner_page": "TopicInspectorPage",
  "safe_stop": "sigint_then_sigterm"
}
```

### 4.1.4 保留终端窗口

需要提供一个内置终端或终端代理面板：

- 显示 ROS2 命令输出。
- 支持手动运行诊断命令。
- 支持复制命令。
- 支持保存日志。
- 支持显示终端所属进程 PID。
- 支持关闭窗口时自动安全停止该终端启动的子进程。
- 支持将终端输出挂接到 `Process Display` 页面。

推荐实现：

- 首版：程序内显示 stdout/stderr 文本流。
- 进阶：嵌入 pseudo-terminal，例如 `pty` + Qt terminal widget。

### 4.1.5 图像 Topic Inspector

对于图像 topic，不能只显示 `sensor_msgs/msg/Image` 的原始字段，还需要提供类似 `rqt_image_view` / `rviz` 的可视化预览。

基础能力：

- 实时显示图像。
- 显示 topic 名称、消息类型、encoding、width、height、step、timestamp。
- 显示实时 FPS、延迟、丢帧估计。
- 支持暂停画面。
- 支持保存当前帧。
- 支持多相机并排预览。
- 支持 base camera / wrist camera / simulation camera 标签。

图像检查能力：

- 鼠标悬停显示当前坐标：
  - x / y。
  - RGB 值。
  - HSV 值。
  - 灰度值。
  - alpha 值，如果存在。
- 点击后锁定采样点。
- 显示一条水平线或垂直线的颜色剖面。
- 显示 RGB 三通道曲线，类似图像处理软件里的颜色幅度图。
- 显示当前帧 RGB histogram。
- 支持选择 ROI，并显示 ROI 的：
  - mean。
  - std。
  - min / max。
  - 黑屏比例。
  - 白屏比例。
  - 饱和像素比例。
  - 模糊度估计。

推荐 UI 形态：

```text
┌──────────────────────────────────────────────┐
│ Image Topic Inspector                         │
├──────────────────────────────────────────────┤
│ left: live image / paused frame                │
│ right: metadata + FPS + timestamp + encoding   │
│ bottom: RGB histogram / line profile           │
└──────────────────────────────────────────────┘
```

颜色剖面示例数据结构：

```json
{
  "topic": "/camera/camera_side/color/image_raw",
  "frame_id": "camera_side_color_optical_frame",
  "sample_mode": "horizontal_line",
  "line_y": 240,
  "x_range": [0, 639],
  "channels": {
    "r": [12, 13, 14],
    "g": [22, 21, 20],
    "b": [30, 31, 29]
  }
}
```

这个能力对机器人采集很重要，因为很多坏数据不是 topic 断了，而是图像曝光、遮挡、颜色异常、相机接错、编码错或腕部相机角度不对。

### 4.1.6 多模态数组 Inspector

除了 RGB 图像，平台还需要为不同模态提供专门的预览 renderer。不要把所有非 RGB 数据都退化为原始数字表格，否则采集人员很难在现场判断传感器是否正常。

建议 renderer：

| modality     | renderer           | 预览内容                                 |
| ------------ | ------------------ | ---------------------------------------- |
| rgb          | image_rgb          | RGB 图像、histogram、RGB 取样            |
| depth        | depth_colormap     | 深度伪彩色图、无效值比例、深度范围       |
| thermal      | heatmap            | 热力图、温度范围、热点检测               |
| lidar        | polar_scan         | 极坐标扫描图、距离曲线、无效 ray 比例    |
| pointcloud   | pointcloud_3d      | 3D 点云、坐标范围、点数                  |
| ultrasound   | line_or_heatmap    | 距离强度曲线或阵列热力图                 |
| event_camera | event_accumulation | 固定时间窗事件累积图、正负 polarity 分布 |
| tactile      | heatmap            | 触觉阵列压力热力图                       |
| force_torque | time_series        | 6 轴力/力矩曲线                          |
| proprio      | time_series        | joint position / velocity / effort 曲线  |
| custom       | table_or_plugin    | 表格、曲线或用户插件                     |

事件相机预览示例：

```yaml
preview:
  renderer: event_accumulation
  accumulation_ms: 30
  positive_color: red
  negative_color: blue
  decay: linear
```

深度图预览示例：

```yaml
preview:
  renderer: depth_colormap
  colormap: turbo
  invalid_value: 0
  clip_min: 0.2
  clip_max: 2.0
  unit: meter
```

### 4.1.7 节点选择

用户可以选择一部分节点进入采集配置，例如：

- 相机节点：
  - `/camera/camera_side`
  - `/camera/camera_wrist`
- 机器人状态节点：
  - `/wx250s/joint_states`
- 动作 topic：
  - `/widowx_action`
- 仿真节点：
  - Genesis 发布的 camera / joint / state / action topic。

选择后进入“采集数据配置”步骤。

---

## 4.2 功能二：采集数据配置

### 4.2.1 自动生成 YAML

系统根据选中的 ROS2 节点和 topic 自动生成一个采集配置 YAML。

示例：

```yaml
project:
  name: catch_the_satellite_2fig
  version: v1
  operator: microsate
  created_at: auto
  environment: physical

robot:
  name: widowx
  model: wx250s
  description: 6-dof WidowX arm with gripper
  base_frame: wx250s/base_link
  end_effector_frame: wx250s/ee_gripper_link
  joint_state_topic: /wx250s/joint_states
  action_topic: /widowx_action
  action_format:
    type: delta_ee_pose_gripper
    dim: 7
    fields:
      - dx
      - dy
      - dz
      - droll
      - dpitch
      - dyaw
      - gripper
    gripper_convention:
      raw_dataset: widowx_open_high
      train_adapter: optional_close_high
      deployment: configurable_invert

instruction:
  text: catch the satellite
  language: en
  task_family: manipulation
  success_condition: gripper reaches and grasps target object

cameras:
  - name: rgb_static
    role: base
    topic: /camera/camera_side/color/image_raw
    type: sensor_msgs/msg/Image
    encoding: rgb8
    fps_target: 10
    crop:
      enabled: false
      x: 0
      y: 0
      width: 640
      height: 480
    resize:
      enabled: true
      width: 224
      height: 224
  - name: rgb_wrist
    role: wrist
    topic: /camera/camera_wrist/color/image_raw
    type: sensor_msgs/msg/Image
    encoding: rgb8
    fps_target: 10
    crop:
      enabled: false
      x: 0
      y: 0
      width: 848
      height: 480
    resize:
      enabled: true
      width: 224
      height: 224

state:
  keys:
    - name: robot_obs
      source_topic: /wx250s/joint_states
      type: sensor_msgs/msg/JointState
      output_dim: 32
      fields:
        - joint_position
        - joint_velocity
        - gripper_state

dataset:
  output_format:
    - npz
    - hdf5
  npz_schema: calvin_style
  hdf5_schema: pi05_calvin_hdf5
  cache_root: /data/dataset/calvin/robot_datasets/gello_widowx/raw_sessions
  merged_root: /data/dataset/calvin/robot_datasets/gello_widowx/merged_calvin
  split: training
  episode_prefix: episode_
  write_language_annotations: true

recording:
  sample_rate_hz: 10
  sync_policy: nearest_timestamp
  max_frame_lag_ms: 100
  min_episode_steps: 5
  auto_drop_empty_frames: true
  auto_drop_invalid_actions: true

genesis:
  enabled: false
  ros_bridge_namespace: /genesis
  scene_file: null
  asset_root: null

ai_validation:
  enabled: true
  provider: openai_compatible
  base_url: ""
  api_key_env: ROBOT_DATA_AI_API_KEY
  model: ""
```

### 4.2.2 YAML 编辑通道

界面需要同时提供：

- 表单式编辑。
- 原始 YAML 文本编辑。
- YAML diff 预览。
- YAML schema 校验。
- 一键恢复自动生成版本。
- 保存为模板。
- 从模板加载。

### 4.2.3 支持配置项

建议尽量全面，至少覆盖：

#### 机器人信息

- robot name。
- robot model。
- DOF。
- end-effector frame。
- base frame。
- gripper convention。
- action dim。
- state dim。
- joint names。
- controller type。

#### 相机信息

- topic。
- role。
- encoding。
- resolution。
- fps。
- crop。
- resize。
- distortion / camera_info topic。
- 是否保存 depth。
- 是否保存 camera intrinsics。

#### 自定义多模态数组信息

平台不应该把数据源限制为 RGB 图像。真实机器人和仿真环境里还会出现深度图、点云、雷达、超声、热成像、事件相机、力矩阵、触觉阵列等多种传感器数据。因此配置层需要提供通用 `streams` / `arrays` 描述能力。

每个数组数据源至少应描述：

- name：写入数据集时的字段名。
- modality：rgb / depth / pointcloud / lidar / ultrasound / event_camera / tactile / force_torque / proprio / custom。
- source：ros2_topic / tcp / file_replay / genesis。
- topic 或 tcp endpoint。
- ROS message type。
- dtype：uint8 / uint16 / float16 / float32 / int32 / structured。
- shape：固定 shape 或 dynamic。
- unit：meter / millimeter / radian / newton / lux / custom。
- timestamp policy。
- compression。
- preview renderer。
- training role：observation / state / action / auxiliary / metadata。

示例：

```yaml
streams:
  - name: rgb_static
    modality: rgb
    source: ros2_topic
    topic: /camera/camera_side/color/image_raw
    message_type: sensor_msgs/msg/Image
    dtype: uint8
    shape: [480, 640, 3]
    encoding: rgb8
    training_role: observation
    preview:
      renderer: image_rgb

  - name: depth_static
    modality: depth
    source: ros2_topic
    topic: /camera/camera_side/depth/image_rect_raw
    message_type: sensor_msgs/msg/Image
    dtype: uint16
    shape: [480, 640]
    unit: millimeter
    training_role: observation
    preview:
      renderer: depth_colormap
      invalid_value: 0
      clip_min: 200
      clip_max: 2000

  - name: lidar_scan
    modality: lidar
    source: ros2_topic
    topic: /scan
    message_type: sensor_msgs/msg/LaserScan
    dtype: float32
    shape: [dynamic]
    unit: meter
    training_role: auxiliary
    preview:
      renderer: polar_scan

  - name: event_camera_front
    modality: event_camera
    source: ros2_topic
    topic: /event_camera/events
    message_type: event_camera_msgs/msg/EventPacket
    dtype: structured
    shape: [dynamic]
    fields:
      - {name: x, dtype: uint16}
      - {name: y, dtype: uint16}
      - {name: t, dtype: int64}
      - {name: polarity, dtype: int8}
    training_role: observation
    preview:
      renderer: event_accumulation
      accumulation_ms: 30

  - name: tactile_grid
    modality: tactile
    source: tcp
    endpoint: 127.0.0.1:10020
    dtype: float32
    shape: [16, 16]
    unit: newton
    training_role: observation
    preview:
      renderer: heatmap
```

#### 任务信息

- instruction。
- language。
- task type。
- target object。
- scene description。
- success criteria。
- failure criteria。
- operator note。

#### 环境信息

- physical / simulation。
- lab name。
- lighting。
- table / workspace。
- object assets。
- background assets。
- Genesis scene file。
- asset version。

#### 数据保存

- raw session path。
- merged dataset path。
- HDF5 path。
- split。
- compression。
- image format。
- metadata JSON。
- 是否 hardlink / copy。

### 4.2.4 支持 Genesis 仿真平台

Genesis 支持要作为一等公民，而不是附加脚本。

需要提供：

- Genesis ROS2 bridge topic 发现。
- 仿真相机 topic 映射。
- 仿真 joint state / action topic 映射。
- scene yaml / asset yaml 读取。
- 仿真环境 reset 信号。
- episode start / stop 信号。
- domain randomization metadata。

Genesis 配置示例：

```yaml
genesis:
  enabled: true
  ros_bridge_namespace: /genesis
  scene_file: /data/genesis/scenes/catch_satellite.yaml
  asset_root: /data/genesis/assets
  sim_fps: 60
  record_fps: 10
  reset_service: /genesis/reset_scene
  step_service: /genesis/step
  cameras:
    - name: rgb_static
      topic: /genesis/camera/static/image
    - name: rgb_wrist
      topic: /genesis/camera/wrist/image
  robot_state_topic: /genesis/robot/joint_states
  action_topic: /genesis/robot/action
  domain_randomization:
    enabled: true
    seed: auto
    fields:
      - lighting
      - object_pose
      - camera_pose
      - material
```

---

## 4.3 功能三：采集、转换与数据治理

### 4.3.1 采集控制

采集面板需要支持：

- 开始采集。
- 暂停采集。
- 停止采集。
- 标记当前 episode 成功 / 失败。
- 删除当前 episode。
- 重采当前 episode。
- 自动 episode 切分。
- 手动 episode 切分。
- 显示当前缓存大小。
- 显示当前帧率。
- 显示各 topic 延迟。
- 显示丢帧计数。

### 4.3.2 数据缓存路径

用户可以选择：

- raw session root。
- task name。
- version。
- split。
- session id。

建议目录结构：

```text
dataset_root/
  raw_sessions/
    <task_name>/
      v1/
        session_20260604_153000/
          config.yaml
          metadata.json
          episodes/
            episode_0000000.npz
            episode_0000001.npz
  merged_calvin/
    <task_name>/
      v1/
        training/
          episode_0000000.npz
          lang_annotations/
            auto_lang_ann.npy
          calvin.hdf5
```

### 4.3.3 NPZ 格式

建议首版保持 CALVIN / 当前训练脚本兼容字段：

```text
rgb_static
rgb_wrist
robot_obs
rel_actions
actions
```

可选字段：

```text
rgb_static_timestamp
rgb_wrist_timestamp
joint_state_timestamp
action_timestamp
camera_info_static
camera_info_wrist
episode_metadata
```

同时需要支持自定义多模态数组字段。NPZ 中每个自定义 stream 建议保存为：

```text
<stream_name>
<stream_name>_timestamp
<stream_name>_metadata
```

例如：

```text
depth_static
depth_static_timestamp
lidar_scan
lidar_scan_timestamp
event_camera_front
event_camera_front_timestamp
tactile_grid
tactile_grid_timestamp
```

对于 dynamic shape 数据，例如 pointcloud、LaserScan、event camera，可以采用两种策略：

1. 单 episode 内保存 object array 或 ragged array，并在 metadata 中记录每帧长度。
2. 保存 flat array + offsets：

```text
event_camera_front_events
event_camera_front_offsets
event_camera_front_timestamp
```

第二种更适合后续转 HDF5 和训练读取。

### 4.3.4 HDF5 格式

建议结构：

```text
calvin.hdf5
  episodes/
    0000000/
      rgb_static
      rgb_wrist
      robot_obs
      rel_actions
      actions
    0000001/
      ...
  annotations/
    info/
      indx
    language/
      ann
  metadata/
    config_yaml
    dataset_version
    robot_description
    stream_descriptors
```

通用 HDF5 stream 结构建议：

```text
calvin.hdf5
  episodes/
    0000000/
      rgb_static
      rgb_wrist
      depth_static
      lidar_scan_values
      lidar_scan_offsets
      event_camera_front_events
      event_camera_front_offsets
      tactile_grid
      robot_obs
      rel_actions
      actions
  streams/
    rgb_static/
      descriptor_json
    depth_static/
      descriptor_json
    lidar_scan/
      descriptor_json
    event_camera_front/
      descriptor_json
```

stream descriptor 示例：

```json
{
  "name": "depth_static",
  "modality": "depth",
  "dtype": "uint16",
  "shape": [480, 640],
  "unit": "millimeter",
  "source": "ros2_topic",
  "topic": "/camera/camera_side/depth/image_rect_raw",
  "message_type": "sensor_msgs/msg/Image",
  "preview_renderer": "depth_colormap",
  "training_role": "observation"
}
```

这样做的好处是：

- 当前 PI05/OpenVLA 训练仍可只读取 `rgb_static`、`rgb_wrist`、`robot_obs`、`rel_actions`。
- 新模型可以按 descriptor 读取 depth、lidar、event camera、tactile 等扩展字段。
- 数据集不会被固定死在 RGB 图像格式。

### 4.3.5 数据集大小测量

展示：

- raw NPZ 总大小。
- HDF5 大小。
- 图像数据占比。
- 单 episode 平均大小。
- 预计上传时间。
- 预计压缩后大小。

### 4.3.6 空帧 / 错误帧检测

自动检测：

- 图像全黑。
- 图像全白。
- 图像尺寸不对。
- 编码不对。
- 深度图全 0 或无效值比例过高。
- 点云 / 雷达为空或距离全越界。
- 超声 / 触觉阵列长时间全 0 或饱和。
- 事件相机事件数异常过低或过高。
- 自定义数组 dtype / shape 与 descriptor 不一致。
- 同一帧重复过多。
- camera timestamp 间隔异常。
- action 维度不对。
- action NaN / Inf。
- gripper 值越界。
- joint state 缺失。
- episode 长度过短。

### 4.3.7 AI 辅助坏帧检测

AI 不应直接替代规则检测，而是作为补充：

- 规则先筛出候选异常帧。
- AI/VLM 判断图像是否可用。
- AI 生成问题描述。
- 用户确认删除或保留。

### 4.3.8 数据预览

预览面板：

- episode 列表。
- 每个 episode 的图像缩略图。
- 多相机同步播放。
- action 曲线。
- gripper 曲线。
- joint 曲线。
- instruction 显示。
- 标记 good / bad / uncertain。
- 删除 episode。
- 导出筛查报告。

### 4.3.9 NPZ 筛查与合并

流程：

1. 扫描 raw NPZ。
2. 检查字段完整性。
3. 检查图像质量。
4. 检查动作维度。
5. 用户删除坏 episode。
6. 生成合并计划 dry-run。
7. 合并 NPZ。
8. 生成 `auto_lang_ann.npy`。
9. 转 HDF5。
10. 校验 HDF5 episode 数、字段、大小。

### 4.3.10 后处理

可选后处理：

- 图像裁切。
- 图像 resize。
- 图像编码转换。
- 去除空帧。
- gripper convention transform。
- action clipping。
- state padding。
- 语言 annotation 重写。
- HDF5 压缩。

---

## 4.4 功能四：文件上传

### 4.4.1 Hugging Face 上传

支持：

- 输入 HF token。
- 登录状态检测。
- 选择 repo。
- 新建 repo。
- 选择 private / public。
- 选择上传内容：
  - raw NPZ。
  - merged NPZ。
  - HDF5。
  - config yaml。
  - metadata json。
  - quality report。
- 上传进度。
- 断点重试。
- 上传后生成 dataset card。

### 4.4.2 SSH / SFTP 上传

支持：

- 输入 host / port / user。
- 密码或 key。
- 自动连接测试。
- 浏览远端目录。
- 新建远端文件夹。
- 选择上传路径。
- 检查剩余磁盘空间。
- 上传前计算本地大小。
- 上传后校验文件大小 / hash。

SSH 配置示例：

```yaml
upload:
  type: ssh
  host: 10.110.10.12
  port: 22
  user: student
  auth:
    method: password_or_key
  remote_root: /data/dataset/calvin/robot_datasets/gello_widowx
```

### 4.4.3 上传安全

必须避免：

- 明文保存 token。
- 明文保存密码。
- 上传路径误覆盖。
- 没确认就删除远端数据。

建议：

- token 存系统 keyring。
- 密码只在会话内保存。
- 覆盖前弹窗确认。
- 上传前生成 manifest。
- 上传后保存 upload report。

---

## 5. AI 能力设计

AI 功能应该是“辅助校验和生成配置”，而不是强依赖。程序在没有 API key 时仍应完整可用。

### 5.1 OpenAI-compatible 接入

配置：

```yaml
ai_provider:
  enabled: true
  api_type: openai_compatible
  base_url: https://api.example.com/v1
  api_key_env: ROBOT_DATA_AI_API_KEY
  model_text: gpt-4.1
  model_vision: gpt-4.1
  timeout_sec: 60
```

### 5.2 AI 任务

- 根据 ROS2 topic 自动解释配置。
- 根据图像生成场景描述。
- 根据 YAML 检查缺失字段。
- 根据采集样本判断坏帧。
- 生成 dataset card。
- 生成训练说明。
- 生成上传说明。

---

## 6. AI 提示词模板

### 6.1 YAML 配置校验提示词

```text
你是机器人数据采集平台的配置审查助手。请检查下面的 YAML 是否足以用于采集机器人多模态数据集。

你的任务：
1. 检查是否包含 robot、cameras、state、action、instruction、dataset、recording、environment 信息。
2. 检查 topic 名称是否命名清晰。
3. 检查图像流、关节状态、动作维度是否可能和 HDF5 / NPZ 输出格式匹配。
4. 检查 gripper convention 是否明确。
5. 检查是否缺少 Genesis 或 physical 环境下的重要字段。
6. 输出必须是结构化 JSON，不要输出 markdown。

输出 JSON schema：
{
  "valid": true,
  "severity": "ok|warning|error",
  "missing_fields": [],
  "suspicious_fields": [],
  "recommended_changes": [],
  "summary": ""
}

待检查 YAML：
{{CONFIG_YAML}}
```

### 6.2 场景描述生成提示词

```text
你是机器人数据集场景描述助手。请根据采集配置和图像预览，生成一个适合写入 dataset metadata 的场景描述。

要求：
1. 描述机器人类型、相机视角、目标物体、操作任务、环境。
2. 不要臆造看不到的信息。
3. 如果信息不确定，写入 "unknown" 或 "not visible"。
4. 输出 YAML 片段，不要输出解释。

输出字段：
scene:
  environment_type:
  robot:
  cameras:
  objects:
  task:
  success_condition:
  risks_or_ambiguities:

采集配置：
{{CONFIG_YAML}}

图像摘要：
{{IMAGE_SUMMARY}}
```

### 6.3 坏帧检测提示词

```text
你是机器人数据质量检查助手。请判断给定帧是否适合保留在训练数据集中。

请关注：
1. 图像是否黑屏、白屏、严重模糊、遮挡、撕裂、曝光异常。
2. 多相机图像是否明显不同步。
3. 是否看不到机器人或任务关键物体。
4. 图像是否与 instruction 明显不匹配。

输出 JSON，不要输出 markdown：
{
  "keep": true,
  "quality": "good|acceptable|bad",
  "issues": [],
  "reason": "",
  "needs_human_review": false
}

Instruction:
{{INSTRUCTION}}

Frame metadata:
{{FRAME_METADATA}}
```

### 6.4 Episode 质量总结提示词

```text
你是机器人 imitation learning 数据集审查助手。请根据 episode 的多帧预览、action 曲线和 gripper 曲线判断这个 episode 是否适合训练。

重点：
1. 是否完成 instruction 对应任务。
2. 轨迹是否连续。
3. gripper 开合是否符合任务逻辑。
4. 是否存在长时间停滞。
5. 是否存在相机空帧或明显错帧。
6. 是否建议删除、保留或人工复查。

输出 JSON：
{
  "episode_decision": "keep|delete|review",
  "task_success_likelihood": 0.0,
  "trajectory_quality": "good|medium|bad",
  "gripper_quality": "good|medium|bad|unknown",
  "visual_quality": "good|medium|bad",
  "issues": [],
  "short_summary": ""
}

Instruction:
{{INSTRUCTION}}

Episode metadata:
{{EPISODE_METADATA}}

Action summary:
{{ACTION_SUMMARY}}

Frame summaries:
{{FRAME_SUMMARIES}}
```

### 6.5 Dataset Card 生成提示词

```text
你是机器人数据集发布助手。请根据 metadata 为 Hugging Face dataset repo 生成 README.md。

要求：
1. 清楚说明数据来源、机器人、相机、任务、格式。
2. 包含字段说明。
3. 包含采集频率、episode 数、数据大小。
4. 包含使用限制和安全注意事项。
5. 包含训练读取示例。
6. 不要夸大数据质量。

输出 markdown：

Dataset metadata:
{{DATASET_METADATA}}
```

### 6.6 ROS2 Topic 自动映射提示词

```text
你是 ROS2 机器人数据采集配置助手。请根据发现到的 ROS2 nodes/topics，推断哪些 topic 应该映射到相机、机器人状态、动作、tf、camera_info。

输出 JSON：
{
  "camera_topics": [
    {
      "name": "",
      "role": "base|wrist|external|unknown",
      "topic": "",
      "message_type": "",
      "confidence": 0.0
    }
  ],
  "state_topics": [],
  "action_topics": [],
  "tf_topics": [],
  "camera_info_topics": [],
  "warnings": [],
  "questions_for_user": []
}

ROS2 graph:
{{ROS_GRAPH_JSON}}
```

---

## 7. 数据 schema 建议

### 7.1 项目配置文件

建议命名：

```text
collection_config.yaml
```

### 7.2 每次采集 session metadata

```json
{
  "session_id": "session_20260604_153000",
  "task_name": "catch_the_satellite_2fig",
  "operator": "microsate",
  "robot": "widowx_wx250s",
  "environment": "physical",
  "ros_domain_id": "0",
  "rmw_implementation": "rmw_fastrtps_cpp",
  "sample_rate_hz": 10,
  "num_episodes": 0,
  "config_file": "collection_config.yaml"
}
```

### 7.3 数据质量报告

```json
{
  "dataset_root": "",
  "num_episodes": 1877,
  "valid_episodes": 1800,
  "deleted_episodes": 77,
  "warnings": [],
  "field_stats": {
    "rgb_static": {},
    "rgb_wrist": {},
    "robot_obs": {},
    "rel_actions": {}
  },
  "gripper_stats": {
    "raw_mean": 0.659,
    "after_transform_mean": 0.341,
    "convention": "widowx_open_high"
  }
}
```

---

## 8. 模块拆分

### 8.1 UI 模块

- `NodeDiscoveryPage`
- `TopicInspectorPage`
- `ConfigEditorPage`
- `RecordingPage`
- `DatasetPreviewPage`
- `ConversionPage`
- `UploadPage`
- `SettingsPage`

### 8.2 后端模块

```text
app/
  core/
    project_manager.py
    config_manager.py
    process_manager.py
  ros/
    graph_discovery.py
    topic_probe.py
    ros_recorder.py
    message_converters.py
  tcp/
    tcp_listener.py
    protocol_parsers.py
  dataset/
    npz_writer.py
    hdf5_writer.py
    validator.py
    preview_index.py
    merge_calvin.py
  ai/
    openai_compatible_client.py
    prompt_templates.py
    validators.py
  upload/
    hf_uploader.py
    ssh_uploader.py
  ui/
    ...
```

---

## 9. MVP 版本建议

### 9.1 MVP 必做

- ROS2 node/topic 列表。
- topic echo / hz 简单预览。
- 运行进程管理页面，能看到并安全停止程序启动的终端、topic echo、topic hz 和采集子进程。
- 图像 topic 实时预览，至少支持 RGB 图像显示、FPS、timestamp、鼠标坐标 RGB 取样。
- 自动生成 YAML。
- 手动编辑 YAML。
- 根据 YAML 采集 NPZ。
- 显示 episode 列表和图像预览。
- 手动删除 episode。
- 合并 NPZ。
- 转 HDF5。
- 上传到 SSH 服务器。

### 9.2 MVP 暂缓

- 内置 AI 图像坏帧检测。
- Hugging Face dataset card 自动生成。
- Genesis 深度集成。
- 高级 terminal emulator。
- 多用户权限。

### 9.3 第二阶段

- AI YAML 校验。
- AI 场景描述生成。
- HF 上传。
- Genesis support。
- 数据质量报告。
- action / gripper 曲线预览。

### 9.4 第三阶段

- 多机器人模板。
- 数据集版本管理。
- 采集任务队列。
- 远程采集控制。
- 自动训练触发。

---

## 10. 风险与注意事项

### 10.1 ROS2 环境风险

- 不同 ROS_DOMAIN_ID 导致发现不到节点。
- RMW 不一致影响 Interbotix / RealSense。
- source 顺序错误。
- topic 类型变化。

应对：

- UI 显示当前环境变量。
- 提供环境检查。
- 保存每次采集的环境快照。

### 10.2 数据同步风险

- 多相机不同步。
- action 和 image 时间戳错位。
- topic 频率不稳定。

应对：

- 显示 topic hz。
- 记录 timestamp。
- 支持 nearest / exact / window sync。

### 10.3 数据格式风险

- 训练脚本期望字段和采集字段不一致。
- gripper convention 不明确。
- HDF5 stats 被 chunk padding 影响。

应对：

- schema 校验。
- metadata 明确记录 transform。
- 对 gripper 单独统计。

### 10.4 上传风险

- token 泄露。
- 覆盖远端数据。
- 大文件中断。

应对：

- token keyring。
- 上传 manifest。
- hash 校验。
- 断点续传。

---

## 11. 当前项目与本平台的关系

当前已有能力：

- CALVIN-style NPZ 数据。
- merged CALVIN root。
- HDF5 转换。
- PI05 HDF5 训练入口。
- OpenVLA 训练入口。
- WidowX ROS2 控制节点。
- PI05 TCP server / ROS2 client。

本平台应该复用：

- `merge_calvin_sessions.py`
- PI05 HDF5 dataset schema。
- OpenVLA CALVIN dataset schema。
- 现有 WidowX topic 约定。
- 现有 gripper convention 记录。

本平台应该补齐：

- 可视化节点发现。
- 可视化 YAML 配置。
- 采集过程质量监控。
- 数据预览 / 删除。
- 上传管理。
- AI 辅助校验。

---

## 12. 建议下一步

1. 先确定技术栈：PySide6 还是 Tauri。
2. 定义 `collection_config.yaml` schema。
3. 把当前 WidowX + RealSense + PI05/OpenVLA 的 topic 作为第一个模板。
4. 做 ROS2 node/topic discovery prototype。
5. 做 NPZ recorder prototype。
6. 接入现有 merge + HDF5 脚本。
7. 做 dataset preview。
8. 做 SSH uploader。
9. 再接 AI 校验。

---

## 12.1 当前实现决策：采集与控制解耦

当前工程只负责数据采集链路，不负责启动传感器节点、控制机械臂或发布动作命令。

已有外部系统可以用类似命令启动：

```bash
ros2 launch hermes_data_collection collect_data.launch.py camera_count:=2 instruction:="catch the satellite"
```

RoboDataset Studio 的职责边界是：

- 发现已经存在的 ROS2 nodes / topics。
- 让用户选择需要监听的 image、JointState 和后续扩展的 action/array streams。
- 根据选择生成 `listener_only` 的 `collection_config.yaml`。
- Recording 页面只订阅已有 topic 并写 NPZ episode。
- 不调用 `ros2 launch` 启动外部采集节点。
- 不向 robot action topic 发布控制命令。

配置中使用：

```yaml
runtime:
  mode: listener_only
  starts_external_nodes: false
  publishes_robot_commands: false
```

`robot.action_topic` 可以作为数据来源或元数据保留，但不是 listener-only 采集的必填项。

---

## 13. 首版项目名称建议

可选：

- RoboDataset Studio
- ROS2 Dataset Workbench
- VLA Data Collector
- Robot Data Forge
- CALVIN Capture Studio

如果项目主要服务 OpenVLA / PI05 / CALVIN 数据，可以暂定：

```text
RoboDataset Studio
```
