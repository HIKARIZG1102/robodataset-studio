# RoboDataset Studio Task Status

更新时间：2026-06-05 00:55 Asia/Shanghai

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
- [ ] 创建或连接 GitHub 仓库并推送阶段成果。

## 已完成项目

第一阶段已完成一个可运行方向的 PySide6 MVP 骨架。它不是最终完整采集平台，但已经把计划书里的主要页面和后台服务边界建立起来：

- UI 层只负责工作台页面和用户交互。
- ROS2 发现、进程管理、数据生成、校验、转换、上传分别放在独立服务模块。
- 没有 ROS2 环境时，仍可以用模拟 episode 测试配置、采集、Review 和 Convert 流程。
- Inspector 页面新增前端模拟图像预览，包含 FPS 显示和鼠标坐标 RGB 采样。
- Recording、Review、Convert、Upload 页面增加了基础前置条件检查。
- 已运行 `python3 -m compileall src`，语法编译通过。
- 已完成本地 git 提交，当前使用 `.git_local` 作为分离 git 仓库目录。
- 已创建 `.venv` 并安装项目依赖。
- 已用 `QT_QPA_PLATFORM=offscreen` 验证 PySide6 主窗口可创建，当前包含 11 个页面。
- 已验证最小数据流程：默认配置 -> mock NPZ episode -> Review scan -> HDF5 convert。

## 遇到的问题

- 当前工作目录的 `.git` 是只读挂载，`git status` 显示这里还不是有效 git 仓库。后续需要在当前工程目录初始化新的 git 仓库。
- 本机 `gh` 命令不可用，推送 GitHub 可能需要使用 `git` + HTTPS 远端，或通过 GitHub API 创建仓库。
- 用户消息中包含 GitHub token，属于敏感凭据。后续推送时只应通过环境变量或交互式凭据使用，不写入文件、不打印到日志。建议推送完成后轮换该 token。
- 系统 Python 环境未安装 `PySide6`，但项目 `.venv` 已安装并可运行 GUI 检查。
- 真实 ROS2 是否已安装还需要继续确认。
- 使用用户提供的 GitHub token 推送时，GitHub 返回 `invalid credentials`，代码未能推送到远端。需要换用有效 token 或本机 GitHub 登录凭据。
- 由于当前目录已有一个不可移动的只读 `.git` 挂载点，不能使用普通 `.git` 目录；已改用 `git --git-dir=.git_local --work-tree=.` 的分离仓库方式。

## 待完成部分

- 前端逻辑：
  - 页面间状态流检查：Project -> Environment -> Discovery -> Config -> Recording -> Review -> Convert -> Upload。
  - 无 project/config/raw data/converted data 时禁用对应操作。
  - 图像 topic 前端预览占位、FPS、坐标/RGB 采样 UI。
  - Process 页面日志查看和停止确认。

- 后端能力：
  - 真实 ROS2 image preview worker。
  - 真实 ROS2 recorder。
  - NPZ 合并计划 dry-run。
  - SSH 上传连接测试和 manifest/hash 校验。

- 工程化：
  - 安装依赖或确认本机环境。
  - 运行导入检查。
  - 初始化 git 仓库。
  - 创建 GitHub 仓库并推送阶段成果。
