# RoboDataset Studio 中文说明

[English README](README.md)

RoboDataset Studio 是一个面向 ROS2 数据采集的桌面软件。前端使用 PySide6，
本地后端使用 FastAPI。它的默认定位是 listener-only：发现已有 ROS2 节点和
topic，订阅数据，记录 session，检查和整理数据，导出 HDF5，并生成上传清单；
默认不向机械臂或相机节点发送控制命令。

## 一台空 Ubuntu 22.04 机器怎么安装

先安装 ROS2，例如 Humble，并确认 `/opt/ros/humble/setup.bash` 存在。然后
clone 仓库：

```bash
git clone https://github.com/HIKARIZG1102/robodataset-studio.git
cd robodataset-studio
```

Docker 安装和本地脚本安装二选一即可。

## 方式 A：Docker 运行

Docker 适合新机器快速启动，因为 Python、Qt、FastAPI 等软件依赖都在镜像里。
宿主机仍需要 Docker、图形桌面，以及用于 ROS 发现的 ROS2 环境。

如果机器还没有 Docker，先安装：

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

执行 `usermod` 后需要注销并重新登录；当前 shell 里还没有 Docker 权限时，可以
先用下面的 sudo 运行命令。

Docker 命令需要在 git clone 下来的仓库根目录运行，也就是包含 `Dockerfile`、
`README.md`、`scripts/` 的目录。使用已经发布的镜像：

```bash
cd robodataset-studio
docker pull ghcr.io/hikarizg1102/robodataset-studio:latest
./scripts/docker_run.sh
```

如果当前登录会话仍然提示没有 Docker 权限：

```bash
cd robodataset-studio
sudo -E env ./scripts/docker_run.sh
```

`scripts/docker_run.sh` 会自动把当前 git clone 下来的仓库目录挂载到容器内：

```text
宿主机当前仓库  ->  /workspace/robodataset-studio
```

不要把 `docker_run.sh` 单独复制到别的目录运行；脚本会根据自己所在位置计算要
挂载的仓库根目录，复制出去会挂错目录。

所以 Docker 里创建的项目、采集到的 `raw_sessions`、review 结果、导出文件、
manifest 和日志，都会落到宿主机这个仓库目录里。宿主机文件管理器可以直接看
到和管理这些文件。

Docker 模式为了避免“容器里看不见宿主机路径”的黑盒问题，会禁止打开或采集到
挂载目录外的路径。项目 root、collect 输出目录都应该放在：

```text
/workspace/robodataset-studio
```

推荐项目目录：

```text
/workspace/robodataset-studio/robodataset/projects
```

如果需要使用 ROS2，启动脚本会尽量挂载 `/opt/ros`，并默认使用 host network、
host IPC、host PID、privileged 模式和共享 `/dev/shm`。这可以贴近宿主机
ROS2/DDS 发现行为，适配依赖 FastDDS 共享内存、相机节点或机器人节点进程命名空间
访问的环境。使用 ROS2 时，先在宿主机 source ROS，再运行同一个启动命令：

```bash
source /opt/ros/humble/setup.bash
./scripts/docker_run.sh
```

如果机器人或相机消息包在额外 overlay 工作空间里，启动前先 source overlay：

```bash
source /opt/ros/humble/setup.bash
source /path/to/overlay/install/setup.bash
./scripts/docker_run.sh
```

如果启动前的 shell 已经 source 过 ROS overlay，Docker 启动脚本会从
`COLCON_PREFIX_PATH` 和 `AMENT_PREFIX_PATH` 自动推断 workspace 根目录，只读挂载
进去，并生成一个临时 setup chain：容器内会依次 source `/opt/ros` 和所有检测到
的 overlay setup 文件。只有自动检测漏掉必需工作空间时，才需要手动填写
`ROS_WORKSPACE_MOUNTS`。容器不会直接复用宿主机的 `PYTHONPATH` 或
`LD_LIBRARY_PATH`，而是通过 source ROS setup 文件重建这些路径。

如果自动检测漏掉了某个 workspace，仍然可以手动覆盖：

```bash
ROS_WORKSPACE_MOUNTS=/path/to/ws1:/path/to/ws2 \
RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
./scripts/docker_run.sh
```

如果想在本机重新构建镜像，而不是使用发布镜像：

```bash
./scripts/docker_build.sh
./scripts/docker_run.sh
```

## 方式 B：本地脚本运行

本地运行会在仓库里创建 `.venv` 或 `.conda-env`，并以 editable 模式安装软件。
本地模式可以像普通软件一样访问仓库外的宿主机路径。

建议先安装这些系统包：

```bash
sudo apt-get update
sudo apt-get install -y \
  python3.10-venv fontconfig fonts-noto-cjk \
  libdbus-1-3 libegl1 libgl1 libglib2.0-0 \
  libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 \
  openssh-client rsync xauth
```

启动：

```bash
./RoboDataset-Studio.sh
```

第一次启动时脚本会自动执行：

```bash
scripts/bootstrap.sh
```

ROS2 Humble 通常使用 Python 3.10，所以不要用 conda/base 的 Python 3.13 直接
运行本软件。需要指定环境时：

```bash
ENV_BACKEND=venv PYTHON_BIN=/usr/bin/python3.10 ./scripts/bootstrap.sh
```

指定 ROS setup 或 RMW：

```bash
ROS_SETUP=/path/to/install/setup.bash ./RoboDataset-Studio.sh
ROBODATASET_RMW_IMPLEMENTATION=rmw_fastrtps_cpp ./RoboDataset-Studio.sh
```

## ROS2 / DDS 适配说明

DDS/RMW 是 ROS2 通信层，不是本软件自己的 pip 依赖。软件会检测当前环境里已安
装的 RMW，并给出可读的 warning/error。

常见开源路径：

- `rmw_fastrtps_cpp` / FastDDS
- `rmw_cyclonedds_cpp` / CycloneDDS

可能存在但依赖额外 runtime 或 license 的路径：

- `rmw_fastrtps_dynamic_cpp`
- `rmw_connextdds`
- `rmw_gurumdds_cpp`
- `rmw_zenoh_cpp`

节点是否能被看见，取决于：

- `ROS_SETUP` 是否 source 正确；
- `ROS_DOMAIN_ID` 是否一致；
- `ROS_LOCALHOST_ONLY` 是否限制为本机；
- 机器网络、组播、VPN、Docker host network；
- topic QoS 是否匹配；
- 自定义消息包是否在当前 ROS workspace 中。

厂商自定义消息不需要提前在软件里列全。软件看到 topic 类型后，会动态尝试加载
对应 `package/msg/Type`。如果外部工作空间装了这个消息包，就能解析；如果没
装，软件会针对这个 topic 报缺失消息包，而不是静默失败。

## 哪些功能不依赖真实机器人

安装完成后，下面功能可以在没有真实机器人时运行：

- 新建/打开项目；
- 配置管理；
- Settings / Environment 检测；
- Logs；
- Tutorial；
- 模拟采集；
- Review scan/check；
- session 删除到回收站；
- merge；
- HDF5 导出；
- upload manifest 生成。

下面功能需要外部条件：

- 真实采集：需要 ROS2 topic 正在发布，且与项目配置匹配；
- Inspector 图像监看：需要 image 或 compressed image topic；
- 上传/校验：需要 SSH 服务器、账号和密码/密钥；
- AI review：需要可用的 OpenAI-compatible API 地址、API key 和模型。

## 常用命令

本地：

```bash
./RoboDataset-Studio.sh
```

Docker：

```bash
./scripts/docker_build.sh
./scripts/docker_run.sh
```

检查 Python 代码：

```bash
python3 -m compileall -q src
```
