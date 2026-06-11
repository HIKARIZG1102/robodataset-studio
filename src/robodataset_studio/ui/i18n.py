from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractButton,
    QLabel,
    QListWidget,
    QMainWindow,
    QTabWidget,
    QTableWidget,
    QWidget,
)


TextMap = dict[str, dict[str, str]]


TEXTS: TextMap = {
    "RoboDataset Studio": {"zh": "RoboDataset Studio", "en": "RoboDataset Studio"},
    "RoboDataset Studio - Process": {"zh": "RoboDataset Studio - 进程", "en": "RoboDataset Studio - Process"},
    "RoboDataset Studio - Settings": {"zh": "RoboDataset Studio - 设置", "en": "RoboDataset Studio - Settings"},
    "1. 配置与 ROS Topic": {"zh": "1. 配置与 ROS Topic", "en": "1. Config & ROS Topics"},
    "2. 采集": {"zh": "2. 采集", "en": "2. Recording"},
    "3. 数据 Review": {"zh": "3. 数据 Review", "en": "3. Data Review"},
    "4. 数据转换": {"zh": "4. 数据转换", "en": "4. Conversion"},
    "5. 上传": {"zh": "5. 上传", "en": "5. Upload"},
    "Project": {"zh": "项目", "en": "Project"},
    "Environment": {"zh": "环境", "en": "Environment"},
    "Discovery": {"zh": "发现", "en": "Discovery"},
    "Inspector": {"zh": "检查器", "en": "Inspector"},
    "Config": {"zh": "配置", "en": "Config"},
    "Process": {"zh": "进程", "en": "Process"},
    "Settings": {"zh": "设置", "en": "Settings"},
    "Browse": {"zh": "浏览", "en": "Browse"},
    "Use gello_widowx preset": {"zh": "使用 gello_widowx 预设", "en": "Use gello_widowx preset"},
    "Save Project": {"zh": "保存项目", "en": "Save Project"},
    "Task name": {"zh": "任务名称", "en": "Task name"},
    "Version": {"zh": "版本", "en": "Version"},
    "Operator": {"zh": "采集员", "en": "Operator"},
    "Dataset root": {"zh": "数据集根目录", "en": "Dataset root"},
    "Project paths": {"zh": "项目路径", "en": "Project paths"},
    "Refresh": {"zh": "刷新", "en": "Refresh"},
    "Use": {"zh": "使用", "en": "Use"},
    "Topic": {"zh": "Topic", "en": "Topic"},
    "Discover ROS2 Graph": {"zh": "发现 ROS2 图", "en": "Discover ROS2 Graph"},
    "Generate Listener Config From Selected Topics": {
        "zh": "根据已选 Topic 生成监听配置",
        "en": "Generate Listener Config From Selected Topics",
    },
    "Nodes": {"zh": "节点", "en": "Nodes"},
    "Topics": {"zh": "Topics", "en": "Topics"},
    "Node": {"zh": "节点", "en": "Node"},
    "Generic topic": {"zh": "通用 Topic", "en": "Generic topic"},
    "Image monitor topic": {"zh": "图像监视 Topic", "en": "Image monitor topic"},
    "Image Topic Preview": {"zh": "图像 Topic 预览", "en": "Image Topic Preview"},
    "Node Info": {"zh": "节点信息", "en": "Node Info"},
    "Topic Echo": {"zh": "Topic Echo", "en": "Topic Echo"},
    "Topic Hz": {"zh": "Topic 频率", "en": "Topic Hz"},
    "Preview Log": {"zh": "预览日志", "en": "Preview Log"},
    "Frame Stats": {"zh": "帧统计", "en": "Frame Stats"},
    "Refresh from Discovery": {"zh": "从发现结果刷新", "en": "Refresh from Discovery"},
    "Start node info": {"zh": "启动节点信息", "en": "Start node info"},
    "Stop node info": {"zh": "停止节点信息", "en": "Stop node info"},
    "Start topic echo": {"zh": "启动 Topic Echo", "en": "Start topic echo"},
    "Stop topic echo": {"zh": "停止 Topic Echo", "en": "Stop topic echo"},
    "Start topic hz": {"zh": "启动 Topic 频率", "en": "Start topic hz"},
    "Stop topic hz": {"zh": "停止 Topic 频率", "en": "Stop topic hz"},
    "Start image monitor": {"zh": "启动图像监视", "en": "Start image monitor"},
    "Stop image monitor": {"zh": "停止图像监视", "en": "Stop image monitor"},
    "Pause preview": {"zh": "暂停预览", "en": "Pause preview"},
    "Resume preview": {"zh": "继续预览", "en": "Resume preview"},
    "Node, generic topic, and image topic are independent selections.": {
        "zh": "节点、通用 Topic 和图像 Topic 可以独立选择。",
        "en": "Node, generic topic, and image topic are independent selections.",
    },
    "Refresh Config From Selected Topics": {
        "zh": "从已选 Topic 刷新配置",
        "en": "Refresh Config From Selected Topics",
    },
    "Apply Form To YAML": {"zh": "应用表单到 YAML", "en": "Apply Form To YAML"},
    "Reload Form From YAML": {"zh": "从 YAML 重新载入表单", "en": "Reload Form From YAML"},
    "Validate": {"zh": "校验", "en": "Validate"},
    "Save collection_config.yaml": {"zh": "保存 collection_config.yaml", "en": "Save collection_config.yaml"},
    "Selected ROS2 topics": {"zh": "已选 ROS2 Topics", "en": "Selected ROS2 topics"},
    "Dataset structure preview": {"zh": "数据集结构预览", "en": "Dataset structure preview"},
    "collection_config.yaml": {"zh": "collection_config.yaml", "en": "collection_config.yaml"},
    "Project name": {"zh": "项目名称", "en": "Project name"},
    "Project environment": {"zh": "项目环境", "en": "Project environment"},
    "Environment type": {"zh": "环境类型", "en": "Environment type"},
    "Workspace": {"zh": "工作空间", "en": "Workspace"},
    "Lighting": {"zh": "光照", "en": "Lighting"},
    "Objects": {"zh": "物体", "en": "Objects"},
    "Notes": {"zh": "备注", "en": "Notes"},
    "Robot name": {"zh": "机器人名称", "en": "Robot name"},
    "Robot model": {"zh": "机器人型号", "en": "Robot model"},
    "Robot description": {"zh": "机器人描述", "en": "Robot description"},
    "Joint count": {"zh": "关节数量", "en": "Joint count"},
    "Joint order": {"zh": "关节顺序", "en": "Joint order"},
    "Base frame": {"zh": "基座 frame", "en": "Base frame"},
    "End effector frame": {"zh": "末端 frame", "en": "End effector frame"},
    "Instruction / prompt": {"zh": "指令 / prompt", "en": "Instruction / prompt"},
    "Language": {"zh": "语言", "en": "Language"},
    "Task family": {"zh": "任务类别", "en": "Task family"},
    "Success condition": {"zh": "成功条件", "en": "Success condition"},
    "Scene description": {"zh": "场景描述", "en": "Scene description"},
    "Sample rate": {"zh": "采集频率", "en": "Sample rate"},
    "Episode duration": {"zh": "Episode 时长", "en": "Episode duration"},
    "Image crop": {"zh": "图像裁切", "en": "Image crop"},
    "Image resize": {"zh": "图像缩放", "en": "Image resize"},
    "Enable crop": {"zh": "启用裁切", "en": "Enable crop"},
    "Enable resize": {"zh": "启用缩放", "en": "Enable resize"},
    "Listener Recording Console": {"zh": "监听式采集控制台", "en": "Listener Recording Console"},
    "This page listens to configured streams and writes dataset episodes. It does not send robot control commands.": {
        "zh": "本页面只监听已配置的数据流并写入 episode，不发送机器人控制命令。",
        "en": "This page listens to configured streams and writes dataset episodes. It does not send robot control commands.",
    },
    "Refresh Listener Plan": {"zh": "刷新监听计划", "en": "Refresh Listener Plan"},
    "Simulate Listener Episode": {"zh": "模拟采集 Episode", "en": "Simulate Listener Episode"},
    "Record ROS2 Episode": {"zh": "录制 ROS2 Episode", "en": "Record ROS2 Episode"},
    "Start capture monitor": {"zh": "启动采集画面监控", "en": "Start capture monitor"},
    "Stop capture monitor": {"zh": "停止采集画面监控", "en": "Stop capture monitor"},
    "Capture monitor topic": {"zh": "采集画面 Topic", "en": "Capture monitor topic"},
    "Capture monitors": {"zh": "采集画面监控", "en": "Capture monitors"},
    "Duration": {"zh": "时长", "en": "Duration"},
    "Modality": {"zh": "模态", "en": "Modality"},
    "Source": {"zh": "来源", "en": "Source"},
    "Topic/Endpoint": {"zh": "Topic/端点", "en": "Topic/Endpoint"},
    "Role": {"zh": "角色", "en": "Role"},
    "Runtime": {"zh": "运行模式", "en": "Runtime"},
    "Episode": {"zh": "Episode", "en": "Episode"},
    "Status": {"zh": "状态", "en": "Status"},
    "Mark": {"zh": "标记", "en": "Mark"},
    "Steps": {"zh": "步数", "en": "Steps"},
    "Size MB": {"zh": "大小 MB", "en": "Size MB"},
    "Missing": {"zh": "缺失", "en": "Missing"},
    "Quality": {"zh": "质量", "en": "Quality"},
    "Fields": {"zh": "字段", "en": "Fields"},
    "Area": {"zh": "区域", "en": "Area"},
    "NPZ": {"zh": "NPZ", "en": "NPZ"},
    "HDF5": {"zh": "HDF5", "en": "HDF5"},
    "Manifest": {"zh": "Manifest", "en": "Manifest"},
    "Scan Episodes": {"zh": "扫描 Episodes", "en": "Scan Episodes"},
    "Status filter": {"zh": "状态过滤", "en": "Status filter"},
    "Manual mark": {"zh": "人工标记", "en": "Manual mark"},
    "Mark Selected": {"zh": "标记选中", "en": "Mark Selected"},
    "Export quality report": {"zh": "导出质量报告", "en": "Export quality report"},
    "Quality Summary": {"zh": "质量汇总", "en": "Quality Summary"},
    "Inspect Current HDF5": {"zh": "检查当前 HDF5", "en": "Inspect Current HDF5"},
    "Scan CALVIN Layout": {"zh": "扫描 CALVIN 布局", "en": "Scan CALVIN Layout"},
    "Selected NPZ Details": {"zh": "已选 NPZ 详情", "en": "Selected NPZ Details"},
    "Current HDF5 Overview": {"zh": "当前 HDF5 概览", "en": "Current HDF5 Overview"},
    "CALVIN Dataset Layout": {"zh": "CALVIN 数据集布局", "en": "CALVIN Dataset Layout"},
    "Session": {"zh": "Session", "en": "Session"},
    "Annotations": {"zh": "标注", "en": "Annotations"},
    "First": {"zh": "首个", "en": "First"},
    "Last": {"zh": "末个", "en": "Last"},
    "Path": {"zh": "路径", "en": "Path"},
    "Merge Dry Run": {"zh": "合并预演", "en": "Merge Dry Run"},
    "Build Merge Dry Run": {"zh": "生成合并预演", "en": "Build Merge Dry Run"},
    "Merge NPZ Sessions": {"zh": "合并 NPZ Sessions", "en": "Merge NPZ Sessions"},
    "Convert NPZ to HDF5": {"zh": "NPZ 转 HDF5", "en": "Convert NPZ to HDF5"},
    "Local path": {"zh": "本地路径", "en": "Local path"},
    "Server profile": {"zh": "服务器配置", "en": "Server profile"},
    "Save server profile": {"zh": "保存服务器配置", "en": "Save server profile"},
    "Load server profile": {"zh": "加载服务器配置", "en": "Load server profile"},
    "Delete server profile": {"zh": "删除服务器配置", "en": "Delete server profile"},
    "Internal IP / Host": {"zh": "内网 IP / Host", "en": "Internal IP / Host"},
    "Public IP / Host": {"zh": "公网 IP / Host", "en": "Public IP / Host"},
    "Port": {"zh": "端口", "en": "Port"},
    "Username": {"zh": "用户名", "en": "Username"},
    "Password": {"zh": "密码", "en": "Password"},
    "Private key path": {"zh": "私钥路径", "en": "Private key path"},
    "Authentication": {"zh": "认证", "en": "Authentication"},
    "Remote directory": {"zh": "远端目录", "en": "Remote directory"},
    "New folder": {"zh": "新建文件夹", "en": "New folder"},
    "Type": {"zh": "类型", "en": "Type"},
    "Size": {"zh": "大小", "en": "Size"},
    "Build upload manifest": {"zh": "生成上传 Manifest", "en": "Build upload manifest"},
    "Verify upload manifest": {"zh": "校验上传 Manifest", "en": "Verify upload manifest"},
    "Connect and list": {"zh": "连接并列目录", "en": "Connect and list"},
    "Up": {"zh": "上级", "en": "Up"},
    "Use current directory": {"zh": "使用当前目录", "en": "Use current directory"},
    "Create folder": {"zh": "创建文件夹", "en": "Create folder"},
    "Check remote space": {"zh": "检查远端空间", "en": "Check remote space"},
    "Start rsync upload": {"zh": "启动 rsync 上传", "en": "Start rsync upload"},
    "Refresh upload progress": {"zh": "刷新上传进度", "en": "Refresh upload progress"},
    "Upload progress": {"zh": "上传进度", "en": "Upload progress"},
    "Verify remote manifest": {"zh": "校验远端 Manifest", "en": "Verify remote manifest"},
    "ID": {"zh": "ID", "en": "ID"},
    "PID": {"zh": "PID", "en": "PID"},
    "Owner": {"zh": "来源页面", "en": "Owner"},
    "Command": {"zh": "命令", "en": "Command"},
    "Tail": {"zh": "日志尾部", "en": "Tail"},
    "Stop Selected": {"zh": "停止选中", "en": "Stop Selected"},
    "Stop All": {"zh": "全部停止", "en": "Stop All"},
    "Selected Process Log": {"zh": "已选进程日志", "en": "Selected Process Log"},
    "Language / 语言": {"zh": "语言", "en": "Language"},
    "Dependency env": {"zh": "依赖环境", "en": "Dependency env"},
    "AI validation": {"zh": "AI 校验", "en": "AI validation"},
    "OpenAI-compatible base URL": {"zh": "OpenAI-compatible Base URL", "en": "OpenAI-compatible base URL"},
    "Model": {"zh": "模型", "en": "Model"},
    "API key": {"zh": "API key", "en": "API key"},
    "Switch / 切换": {"zh": "切换语言", "en": "Switch language"},
    "Python env: project-local .venv or .conda-env": {
        "zh": "Python 环境：项目本地 .venv 或 .conda-env",
        "en": "Python env: project-local .venv or .conda-env",
    },
    "AI settings are kept in Settings and are not written to collection_config.yaml.": {
        "zh": "AI 设置只保存在 Settings，不写入 collection_config.yaml。",
        "en": "AI settings are kept in Settings and are not written to collection_config.yaml.",
    },
}


def normalize_language(language: str) -> str:
    return "en" if language == "en" else "zh"


def text(key_or_text: str, language: str) -> str:
    language = normalize_language(language)
    key = _canonical_key(key_or_text)
    if key is None:
        return key_or_text
    return TEXTS[key].get(language, key)


def apply_i18n(root: QWidget, language: str) -> None:
    language = normalize_language(language)
    title_key = root.property("i18n_title_key")
    if isinstance(root, QMainWindow) and title_key:
        root.setWindowTitle(text(str(title_key), language))

    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        if isinstance(widget, QMainWindow):
            title_key = widget.property("i18n_title_key")
            if title_key:
                widget.setWindowTitle(text(str(title_key), language))
        if isinstance(widget, QAbstractButton):
            widget.setText(text(widget.text(), language))
        elif isinstance(widget, QLabel):
            widget.setText(text(widget.text(), language))
        elif isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                widget.setTabText(index, text(widget.tabText(index), language))
        elif isinstance(widget, QTableWidget):
            for column in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(column)
                if item is not None:
                    item.setText(text(item.text(), language))
        elif isinstance(widget, QListWidget):
            for row in range(widget.count()):
                item = widget.item(row)
                item.setText(text(item.text(), language))


def _canonical_key(value: str) -> str | None:
    if value in TEXTS:
        return value
    for key, translations in TEXTS.items():
        if value in translations.values():
            return key
    return None
