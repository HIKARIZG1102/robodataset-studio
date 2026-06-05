# RoboDataset Studio Task Status

更新时间：2026-06-05 17:58 Asia/Shanghai

## 当前任务清单

- [x] 读取并分析项目计划书。
- [x] 复制计划书到工程目录：`docs/project_plan.md`。
- [x] 搭建 PySide6 项目骨架。
- [x] 建立核心分层：`core`、`ros`、`dataset`、`upload`、`ui`。
- [x] 实现基础桌面页面：Project、Environment、Discovery、Inspector、Config、Recording、Review、Convert、Upload、Process、Settings。
- [x] 实现自动生成 `collection_config.yaml` 的后端逻辑。
- [x] 实现 ROS2 node/topic/service 命令发现入口。
- [x] 实现后台进程管理器，支持启动、刷新、SIGINT/SIGTERM 安全停止。
- [x] 实现模拟 NPZ episode 生成。
- [x] 实现 NPZ 扫描和 HDF5 转换。
- [x] 完善第一段前端页面状态流和关键步骤限制。
- [x] 完善第一段图像 Topic Inspector 的前端预览逻辑。
- [x] 增加第一段前端通知和错误处理。
- [x] 增加基础语法编译检查。
- [x] 安装 PySide6 依赖并启动 GUI 验证。
- [x] 使用 `.git_local` 初始化分离 git 仓库并提交阶段成果。
- [x] 只读了解远端 `gello_widowx` 数据集结构。
- [x] 将前端 Recording 页面改为监听式采集控制台，不涉及机器人控制。
- [x] 增加 CALVIN 数据集布局扫描前端逻辑。
- [x] 增加 Convert 页面 merge dry-run 计划表。
- [x] Review 页面增加单个 NPZ 字段详情和 HDF5 概览。
- [x] Process 页面增加选中进程日志详情和停止确认。
- [x] Upload 页面增加上传前 manifest/hash 生成和本地校验。
- [x] 根据新引导要求将 UI 调整为四个主板块：配置与 ROS Topic、采集、数据转换、上传；Process/Settings 移到角落工具。
- [x] Inspector 支持从 Discovery 选择 node/topic，并对图像 topic 做真实 ROS2 实时预览。
- [x] Inspector 拆分 Node Info / Topic Echo / Topic Hz / Preview Log 终端面板，并为每个 Start 增加 Stop 和安全退出。
- [x] Inspector 图像预览增加播放 FPS、暂停冻结真实帧和基于真实帧的亮度/RGB/曝光风险统计；日志面板上限调整为 2000 行。
- [x] 修复 image preview 使用固定 ROS node 名导致旧订阅残留/误判的问题，Preview Log 增加真实 frame 计数、encoding、size。
- [x] Image preview 改为 latest-frame single-slot buffer，自动显示真实 width/height/encoding/step/FPS，并扩展深度图 encoding 显示。
- [x] Image preview 改为 RViz 风格 pull-based latest-frame 渲染：订阅线程不按帧发 Qt signal，Stop 后清空 worker/UI buffer 和 pixmap。
- [x] Image preview 显示面板改为 paintEvent 自绘 QImage，Stop/close 时断开 worker signal，降低闪退和 QLabel pixmap 缓存问题。
- [x] Image preview worker 改为 raw bytes latest-slot：ROS callback 只保存最新 raw bytes 和 metadata，UI display timer 按需转换，减少回调线程 CPU/内存压力。
- [x] 创建或连接 GitHub 仓库并推送阶段成果。
- [x] 增加第一版真实监听式 ROS2 image recorder，可按配置订阅 `sensor_msgs/msg/Image` 并写入 NPZ episode。
- [x] 增加可执行 NPZ session merge：按 session 扫描 raw `training/episode_*.npz`，重编号复制到 merged training，并写 `merge_manifest.json`。
- [x] Upload 增加 SSH 连接测试和远端 manifest size/hash 校验后台任务入口。
- [x] 增加后端 smoke tests，覆盖图像 encoding 转换、CALVIN session merge、upload manifest 和 SSH target 解析。
- [x] 真实 ROS2 recorder 增加 `sensor_msgs/msg/JointState` 订阅，按采样节拍写入 `robot_obs`。

## 已完成项目

第一阶段已完成一个可运行方向的 PySide6 MVP 骨架。它不是最终完整采集平台，但已经把计划书里的主要页面和后台服务边界建立起来：

- UI 层只负责工作台页面和用户交互。
- ROS2 发现、进程管理、数据生成、校验、转换、上传分别放在独立服务模块。
- 没有 ROS2 环境时，仍可以用模拟 episode 测试配置、采集、Review 和 Convert 流程。
- Inspector 页面可从 Discovery 结果选择 node/topic，支持 node info、topic echo、topic hz；Node Info / Topic Echo / Topic Hz / Preview Log 分独立终端面板显示，每个面板最多保留 2000 行，并支持成对 Stop；对 `sensor_msgs/msg/Image` 支持真实 ROS2 订阅预览、播放 FPS、暂停冻结真实帧、FPS 显示、鼠标坐标 RGB 采样和真实帧亮度/RGB/过曝欠曝统计。
- Recording、Review、Convert、Upload 页面增加了基础前置条件检查。
- 已运行 `python3 -m compileall src`，语法编译通过。
- 已完成本地 git 提交，当前使用 `.git_local` 作为分离 git 仓库目录。
- 已创建 `.venv` 并安装项目依赖。
- 已用 `QT_QPA_PLATFORM=offscreen` 验证 PySide6 主窗口可创建，当前包含 4 个主板块，配置区和采集区保留子页面 tabs。
- 已验证最小数据流程：默认配置 -> mock NPZ episode -> Review scan -> HDF5 convert。
- 已确认 `gello_widowx` 数据集在 Spaceman_Server 的 `/data/dataset/calvin/robot_datasets/gello_widowx`。
- 已新增 [docs/data_format_notes.md](docs/data_format_notes.md)，记录远端数据格式和对当前项目的影响。
- Project 页面增加 `gello_widowx` 数据集根路径预设。
- Recording 页面新增监听 stream 表格，明确只监听数据源并写 episode，不发送控制命令。
- Review 页面新增 CALVIN layout 扫描表，支持查看 raw/merged 任务版本、NPZ 数、HDF5 和 manifest 状态。
- Convert 页面新增 merge dry-run 表，按 `raw_sessions/<task>/<version>/<session>/training` 扫描 episode 和 `auto_lang_ann.npy`。
- Review 页面新增选中 NPZ 字段详情，包括 shape、dtype、缺失必需字段；新增当前 HDF5 概览，包括 episode 数、metadata attrs 和首个 episode 字段。
- Process 页面新增选中进程 stdout/stderr tail 详情，并在停止单个或全部运行中进程前弹出确认。
- Upload 页面新增 `upload_manifest.json` 生成和本地 hash 校验，上传前会自动刷新 manifest。
- `docs/project_plan.md` 已更新为四段式主工作区信息架构；实际主窗口同步改为四个主导航项，原有 Project / Environment / Discovery / Inspector / Config / Recording / Review / Convert / Upload 功能均保留为板块内页面。
- 已用 `/usb_camera_test_node` 发布的 `/usb_camera/image_raw` 验证真实 ROS2 图像 topic 可被发现和解析为 RGB frame。
- Inspector 图像预览改为专用 image topic 下拉框，只列出 `sensor_msgs/msg/Image`，避免误选 `/parameter_events` 等非图像 topic；ProcessManager 停止流程增强为 SIGINT -> SIGTERM -> SIGKILL。
- Inspector 暂停后的 Frame Stats 明确只展示从当前真实图像像素检测出的统计，不伪造 `sensor_msgs/Image` 未提供的曝光时间或白平衡增益。
- 当前项目外真实摄像头测试节点：`/real_usb_camera_node` 发布 `/usb_camera/image_raw [sensor_msgs/msg/Image]`，encoding=`rgb8`，size=`640x480`，实测约 9-11 FPS；Qt worker 已验证可收到真实帧。
- 已验证 Inspector UI display loop 可以实时显示真实相机帧：`640x480 rgb8 step=1920`，4.5 秒内显示序列推进到 37，QLabel pixmap 非空。
- 已验证 pull-based 预览：真实相机帧可显示，Stop 后 `_latest_frame`、display sequence 和 pixmap 均清空。
- 已验证自绘 preview loop：真实相机显示序列可推进，Stop 后 preview widget frame 清空；额外验证 stop cleanup 后 worker/thread/latest frame 均为空。
- 已验证 raw-slot preview：真实相机显示序列可推进到 58；当前项目外 `real_usb_camera_publisher.py` 测试源本身 Python 进程 CPU 很高，后续应替换为正式 camera driver 或优化测试 publisher。
- 已再次运行 `.venv/bin/python -m compileall src` 和 PySide6 offscreen 主窗口检查，均通过。
- 已连接并推送到 `https://github.com/HIKARIZG1102/robodataset-studio.git` 的 `main` 分支。
- 已用当前真实 `/usb_camera/image_raw [sensor_msgs/msg/Image]` 验证 ROS2 recorder 后端：1 秒采集写出 `episode_0000000.npz`，包含 `rgb_static (3, 480, 640, 3) uint8`、`robot_obs`、`rel_actions`、`actions` 和 `episode_metadata`。
- 已用临时双 session mock 数据验证 NPZ merge：输出连续 `episode_0000000.npz`、`episode_0000001.npz`，并生成 `merge_manifest.json`。
- 已验证 SSH target parser 和连接测试后台任务可启动/停止；远端校验需要真实 SSH target 后在 Process 页面查看结果。
- 已安装 dev 依赖并运行 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`，3 个后端 smoke tests 全部通过；直接 pytest 会被 ROS2 `launch_testing` 外部插件自动加载影响，当前用禁用自动插件方式规避。
- 已为 JointState -> `robot_obs` padding 增加测试，当前 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q` 为 4 passed。

## 遇到的问题

- 当前工作目录的 `.git` 是只读挂载，`git status` 显示这里还不是有效 git 仓库。后续需要在当前工程目录初始化新的 git 仓库。
- 本机 `gh` 命令不可用，推送 GitHub 可能需要使用 `git` + HTTPS 远端，或通过 GitHub API 创建仓库。
- 用户消息中包含 GitHub token，属于敏感凭据。后续推送时只应通过环境变量或交互式凭据使用，不写入文件、不打印到日志。建议推送完成后轮换该 token。
- 系统 Python 环境未安装 `PySide6`，但项目 `.venv` 已安装并可运行 GUI 检查。
- 真实 ROS2 是否已安装还需要继续确认。
- 曾尝试错误仓库名导致 GitHub 返回 `Repository not found`；已定位真实仓库为 `HIKARIZG1102/robodataset-studio` 并成功推送。
- 由于当前目录已有一个不可移动的只读 `.git` 挂载点，不能使用普通 `.git` 目录；已改用 `git --git-dir=.git_local --work-tree=.` 的分离仓库方式。
- `gello_widowx` 数据集路径在 Spaceman_Server 上存在；在 microsate_widowx 上该精确路径不存在。

## 待完成部分

- 前端逻辑：
  - 页面间状态流继续增强：Project -> Environment -> Discovery -> Config -> Recording -> Review -> Convert -> Upload。

- 后端能力：
  - 真实监听式 ROS2 recorder 继续扩展到 action/通用数组 stream，并加入更严格同步策略。
  - NPZ merge 继续扩展语言 annotation 合并策略，进一步兼容 `merge_calvin_sessions.py`。
  - SSH 上传继续扩展远端目录浏览、新建目录、剩余空间检查。

- 工程化：
  - 安装依赖或确认本机环境。
  - 运行导入检查。
  - 初始化 git 仓库。
  - 持续补充自动化 smoke tests / pytest，覆盖 GUI 状态流和 ROS worker 清理。
