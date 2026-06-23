from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QTabWidget,
    QTableWidget,
    QWidget,
)


TEXTS: dict[str, dict[str, str]] = {
    "RoboDataset Studio V3": {"zh": "RoboDataset Studio V3", "en": "RoboDataset Studio V3"},
    "File": {"zh": "文件", "en": "File"},
    "New Project": {"zh": "新建项目", "en": "New Project"},
    "Open Project": {"zh": "打开项目", "en": "Open Project"},
    "Exit": {"zh": "退出", "en": "Exit"},
    "Config": {"zh": "配置", "en": "Config"},
    "Config Library": {"zh": "配置库", "en": "Config Library"},
    "Current Project Config": {"zh": "当前项目配置", "en": "Current Project Config"},
    "Projects": {"zh": "项目", "en": "Projects"},
    "Configs": {"zh": "配置", "en": "Configs"},
    "Open Project Folder": {"zh": "打开项目文件夹", "en": "Open Project Folder"},
    "Properties": {"zh": "属性", "en": "Properties"},
    "Rename": {"zh": "重命名", "en": "Rename"},
    "Permanent Delete": {"zh": "永久删除", "en": "Permanent Delete"},
    "Open Config": {"zh": "打开配置", "en": "Open Config"},
    "Open Logs": {"zh": "打开日志", "en": "Open Logs"},
    "Tools": {"zh": "工具", "en": "Tools"},
    "Collect": {"zh": "采集", "en": "Collect"},
    "Data Review": {"zh": "数据检查", "en": "Data Review"},
    "Review": {"zh": "检查", "en": "Review"},
    "Convert": {"zh": "转换", "en": "Convert"},
    "Upload": {"zh": "上传", "en": "Upload"},
    "AI Assist": {"zh": "AI 辅助", "en": "AI Assist"},
    "AI": {"zh": "AI", "en": "AI"},
    "Logs": {"zh": "日志", "en": "Logs"},
    "Logs / Tasks": {"zh": "日志 / 任务", "en": "Logs / Tasks"},
    "Refresh Tasks": {"zh": "刷新任务", "en": "Refresh Tasks"},
    "Tasks and log files": {"zh": "任务和日志文件", "en": "Tasks and log files"},
    "Selected log": {"zh": "选中日志", "en": "Selected log"},
    "Inspector": {"zh": "检查器", "en": "Inspector"},
    "Settings": {"zh": "设置", "en": "Settings"},
    "Zoom In": {"zh": "放大界面", "en": "Zoom In"},
    "Zoom Out": {"zh": "缩小界面", "en": "Zoom Out"},
    "Reset Zoom": {"zh": "重置缩放", "en": "Reset Zoom"},
    "Split Left": {"zh": "向左拆分", "en": "Split Left"},
    "Split Right": {"zh": "向右拆分", "en": "Split Right"},
    "Split Up": {"zh": "向上拆分", "en": "Split Up"},
    "Split Down": {"zh": "向下拆分", "en": "Split Down"},
    "Merge All Panes": {"zh": "合并所有分屏", "en": "Merge All Panes"},
    "Help": {"zh": "帮助", "en": "Help"},
    "Tutorial": {"zh": "操作教程", "en": "Tutorial"},
    "About": {"zh": "关于", "en": "About"},
    "Refresh Nodes/Topics": {"zh": "刷新节点/Topics", "en": "Refresh Nodes/Topics"},
    "Refreshing...": {"zh": "刷新中...", "en": "Refreshing..."},
    "Project: none | Config: none": {"zh": "项目：无 | 配置：无", "en": "Project: none | Config: none"},
    "Create or open a project to start.": {"zh": "创建或打开项目后开始。", "en": "Create or open a project to start."},
    "Project Config": {"zh": "项目配置", "en": "Project Config"},
    "Project Overview": {"zh": "项目概览", "en": "Project Overview"},
    "Project files": {"zh": "项目文件", "en": "Project files"},
    "Selected file": {"zh": "选中文件", "en": "Selected file"},
    "Refresh From Project": {"zh": "从项目刷新", "en": "Refresh From Project"},
    "Refresh Library": {"zh": "刷新配置库", "en": "Refresh Library"},
    "Load Config Into Project": {"zh": "加载配置到项目", "en": "Load Config Into Project"},
    "Preview": {"zh": "预览", "en": "Preview"},
    "Save Project Config": {"zh": "保存项目配置", "en": "Save Project Config"},
    "Library config": {"zh": "配置库条目", "en": "Library config"},
    "Load Settings": {"zh": "加载设置", "en": "Load Settings"},
    "Save Settings": {"zh": "保存设置", "en": "Save Settings"},
    "General": {"zh": "通用", "en": "General"},
    "Advanced YAML": {"zh": "高级 YAML", "en": "Advanced YAML"},
    "Language": {"zh": "语言", "en": "Language"},
    "Enable AI": {"zh": "启用 AI", "en": "Enable AI"},
    "OpenAI-compatible base URL": {"zh": "OpenAI 兼容 Base URL", "en": "OpenAI-compatible base URL"},
    "API key": {"zh": "API key", "en": "API key"},
    "Default model": {"zh": "默认模型", "en": "Default model"},
    "Refresh models": {"zh": "刷新模型", "en": "Refresh models"},
    "Timeout": {"zh": "超时", "en": "Timeout"},
    "Prompt budget": {"zh": "Prompt 字符预算", "en": "Prompt budget"},
    "Probe stdout budget": {"zh": "探测输出预算", "en": "Probe stdout budget"},
    "Model status": {"zh": "模型状态", "en": "Model status"},
    "AI settings are stored locally and are not written into total_config.yaml.": {
        "zh": "AI 设置只保存在本机，不写入 total_config.yaml。",
        "en": "AI settings are stored locally and are not written into total_config.yaml.",
    },
    "List Models": {"zh": "列出模型", "en": "List Models"},
    "Default Config Prompt": {"zh": "默认配置 Prompt", "en": "Default Config Prompt"},
    "Default Review Prompt": {"zh": "默认检查 Prompt", "en": "Default Review Prompt"},
    "Send": {"zh": "发送", "en": "Send"},
    "AI Prompt": {"zh": "AI Prompt", "en": "AI Prompt"},
    "AI Response": {"zh": "AI 回复", "en": "AI Response"},
    "AI base URL, API key, model, and timeout are configured in Settings.": {
        "zh": "AI base URL、API key、模型和超时在设置页配置。",
        "en": "AI base URL, API key, model, and timeout are configured in Settings.",
    },
    "Listener Recording Console": {"zh": "监听式采集控制台", "en": "Listener Recording Console"},
    "Uses the current dataset_config.yaml. Image monitors are available from the global Inspector panel.": {
        "zh": "使用当前 dataset_config.yaml。图像监视在全局检查器面板中使用。",
        "en": "Uses the current dataset_config.yaml. Image monitors are available from the global Inspector panel.",
    },
    "Stop mode": {"zh": "停止方式", "en": "Stop mode"},
    "Manual": {"zh": "手动", "en": "Manual"},
    "Duration": {"zh": "时长", "en": "Duration"},
    "Sample count": {"zh": "样本数", "en": "Sample count"},
    "Samples": {"zh": "样本", "en": "Samples"},
    "Refresh Listener Plan": {"zh": "刷新监听计划", "en": "Refresh Listener Plan"},
    "Check Nodes": {"zh": "检查节点/Topic", "en": "Check Nodes"},
    "Simulate Listener Episode": {"zh": "模拟采集 Episode", "en": "Simulate Listener Episode"},
    "Start Recording": {"zh": "开始录制", "en": "Start Recording"},
    "Stop Recording": {"zh": "停止录制", "en": "Stop Recording"},
    "Name": {"zh": "名称", "en": "Name"},
    "Modality": {"zh": "模态", "en": "Modality"},
    "Source": {"zh": "来源", "en": "Source"},
    "Topic/Endpoint": {"zh": "Topic/端点", "en": "Topic/Endpoint"},
    "Type": {"zh": "类型", "en": "Type"},
    "Role": {"zh": "角色", "en": "Role"},
    "Use": {"zh": "使用", "en": "Use"},
    "Session": {"zh": "Session", "en": "Session"},
    "Episodes": {"zh": "Episodes", "en": "Episodes"},
    "Status": {"zh": "状态", "en": "Status"},
    "Path": {"zh": "路径", "en": "Path"},
    "Select All": {"zh": "全选", "en": "Select All"},
    "Clear": {"zh": "清空选择", "en": "Clear"},
    "Invert": {"zh": "反选", "en": "Invert"},
    "Scan Sessions": {"zh": "扫描 Sessions", "en": "Scan Sessions"},
    "Merge Sessions": {"zh": "合并 Sessions", "en": "Merge Sessions"},
    "Convert To HDF5": {"zh": "转换为 HDF5", "en": "Convert To HDF5"},
    "Raw sessions root": {"zh": "Raw sessions 根目录", "en": "Raw sessions root"},
    "Output dir": {"zh": "输出目录", "en": "Output dir"},
    "Output name": {"zh": "输出名称", "en": "Output name"},
    "Browse": {"zh": "浏览", "en": "Browse"},
    "Overview": {"zh": "概览", "en": "Overview"},
    "Refresh Overview": {"zh": "刷新概览", "en": "Refresh Overview"},
    "Episode Review": {"zh": "Episode 检查", "en": "Episode Review"},
    "HDF5 Inspect": {"zh": "HDF5 检查", "en": "HDF5 Inspect"},
    "Review session root": {"zh": "Session 根目录", "en": "Review session root"},
    "Use Current Session": {"zh": "使用当前 Session", "en": "Use Current Session"},
    "Scan Session": {"zh": "扫描 Session", "en": "Scan Session"},
    "Run Local Checks": {"zh": "运行本地检查", "en": "Run Local Checks"},
    "Export Quality Report": {"zh": "导出质量报告", "en": "Export Quality Report"},
    "Status filter": {"zh": "状态过滤", "en": "Status filter"},
    "Manual mark": {"zh": "人工标记", "en": "Manual mark"},
    "Mark Selected": {"zh": "标记选中", "en": "Mark Selected"},
    "Delete Selected": {"zh": "删除选中", "en": "Delete Selected"},
    "Quality Summary": {"zh": "质量汇总", "en": "Quality Summary"},
    "Selected NPZ Details": {"zh": "选中 NPZ 详情", "en": "Selected NPZ Details"},
    "AI Review": {"zh": "AI 检查", "en": "AI Review"},
    "Default AI Review Prompt": {"zh": "默认 AI 检查 Prompt", "en": "Default AI Review Prompt"},
    "Send AI Review": {"zh": "发送 AI 检查", "en": "Send AI Review"},
    "Inspect HDF5": {"zh": "检查 HDF5", "en": "Inspect HDF5"},
    "Run HDF5 Checks": {"zh": "运行 HDF5 检查", "en": "Run HDF5 Checks"},
    "HDF5 Overview": {"zh": "HDF5 概览", "en": "HDF5 Overview"},
    "HDF5 Check Summary": {"zh": "HDF5 检查汇总", "en": "HDF5 Check Summary"},
    "HDF5 Check Results": {"zh": "HDF5 检查结果", "en": "HDF5 Check Results"},
    "Episode": {"zh": "Episode", "en": "Episode"},
    "Mark": {"zh": "标记", "en": "Mark"},
    "Steps": {"zh": "步数", "en": "Steps"},
    "Size MB": {"zh": "大小 MB", "en": "Size MB"},
    "Missing": {"zh": "缺失", "en": "Missing"},
    "Quality": {"zh": "质量", "en": "Quality"},
    "Fields": {"zh": "字段", "en": "Fields"},
    "Scope": {"zh": "范围", "en": "Scope"},
    "Issue": {"zh": "问题", "en": "Issue"},
    "Detail": {"zh": "详情", "en": "Detail"},
    "Local source": {"zh": "本地源", "en": "Local source"},
    "File or folder": {"zh": "文件或文件夹", "en": "File or folder"},
    "Check Dependencies": {"zh": "检查依赖", "en": "Check Dependencies"},
    "Build Manifest": {"zh": "生成 Manifest", "en": "Build Manifest"},
    "Verify Local Manifest": {"zh": "校验本地 Manifest", "en": "Verify Local Manifest"},
    "Server and remote directory": {"zh": "服务器与远端目录", "en": "Server and remote directory"},
    "Reload from project config": {"zh": "从项目配置重载", "en": "Reload from project config"},
    "Host / IP": {"zh": "Host / IP", "en": "Host / IP"},
    "Port": {"zh": "端口", "en": "Port"},
    "Username": {"zh": "用户名", "en": "Username"},
    "Password": {"zh": "密码", "en": "Password"},
    "Private key path": {"zh": "私钥路径", "en": "Private key path"},
    "Authentication": {"zh": "认证", "en": "Authentication"},
    "Remote directory": {"zh": "远端目录", "en": "Remote directory"},
    "Connect and list": {"zh": "连接并列目录", "en": "Connect and list"},
    "Up": {"zh": "上级", "en": "Up"},
    "Use Current Directory": {"zh": "使用当前目录", "en": "Use Current Directory"},
    "Check Remote Space": {"zh": "检查远端空间", "en": "Check Remote Space"},
    "New folder": {"zh": "新建文件夹", "en": "New folder"},
    "Create Folder": {"zh": "创建文件夹", "en": "Create Folder"},
    "Transfer": {"zh": "传输", "en": "Transfer"},
    "Start rsync upload": {"zh": "开始 rsync 上传", "en": "Start rsync upload"},
    "Repair / Resume verified upload": {"zh": "修复 / 续传已校验上传", "en": "Repair / Resume verified upload"},
    "Verify remote manifest": {"zh": "校验远端 Manifest", "en": "Verify remote manifest"},
    "Cancel current task": {"zh": "取消当前任务", "en": "Cancel current task"},
    "Refresh task": {"zh": "刷新任务", "en": "Refresh task"},
    "Local manifest preview": {"zh": "本地 Manifest 预览", "en": "Local manifest preview"},
    "Remote directory listing": {"zh": "远端目录列表", "en": "Remote directory listing"},
    "Size": {"zh": "大小", "en": "Size"},
    "SHA256": {"zh": "SHA256", "en": "SHA256"},
    "Topic Inspector": {"zh": "Topic 检查器", "en": "Topic Inspector"},
    "Image Monitor": {"zh": "图像监视", "en": "Image Monitor"},
    "Node": {"zh": "节点", "en": "Node"},
    "Start node info": {"zh": "开始节点信息", "en": "Start node info"},
    "Stop node info": {"zh": "停止节点信息", "en": "Stop node info"},
    "Generic topic": {"zh": "通用 Topic", "en": "Generic topic"},
    "Start topic echo": {"zh": "开始 Topic Echo", "en": "Start topic echo"},
    "Stop topic echo": {"zh": "停止 Topic Echo", "en": "Stop topic echo"},
    "Start topic hz": {"zh": "开始 Topic 频率", "en": "Start topic hz"},
    "Stop topic hz": {"zh": "停止 Topic 频率", "en": "Stop topic hz"},
    "Node Info": {"zh": "节点信息", "en": "Node Info"},
    "Topic Echo": {"zh": "Topic Echo", "en": "Topic Echo"},
    "Topic Hz": {"zh": "Topic 频率", "en": "Topic Hz"},
    "Image monitor topic": {"zh": "图像监视 Topic", "en": "Image monitor topic"},
    "Monitor project image": {"zh": "监视项目图像", "en": "Monitor project image"},
    "Start image monitor": {"zh": "开始图像监视", "en": "Start image monitor"},
    "Stop image monitor": {"zh": "停止图像监视", "en": "Stop image monitor"},
    "Pause / Resume": {"zh": "暂停 / 继续", "en": "Pause / Resume"},
    "Frame stats": {"zh": "帧统计", "en": "Frame stats"},
    "Preview Log": {"zh": "预览日志", "en": "Preview Log"},
    "Frame Stats": {"zh": "帧统计", "en": "Frame Stats"},
    "Apply Selected Topics To Config": {"zh": "应用已选 Topics 到配置", "en": "Apply Selected Topics To Config"},
    "Node Details": {"zh": "节点详情", "en": "Node Details"},
    "Use the top toolbar Refresh Nodes/Topics button to update the global ROS graph.": {
        "zh": "使用顶部工具栏的刷新节点/Topics按钮更新全局 ROS 图。",
        "en": "Use the top toolbar Refresh Nodes/Topics button to update the global ROS graph.",
    },
    "Selected node": {"zh": "选中节点", "en": "Selected node"},
    "Discovered topics": {"zh": "已发现 Topics", "en": "Discovered topics"},
    "Topics are grouped by their top-level ROS namespace. Expand a group to choose individual topics.": {
        "zh": "Topics 按顶层 ROS 命名空间分组。展开分组后选择单个 topic。",
        "en": "Topics are grouped by their top-level ROS namespace. Expand a group to choose individual topics.",
    },
    "Config name": {"zh": "配置名称", "en": "Config name"},
    "Library": {"zh": "配置库", "en": "Library"},
    "Refresh": {"zh": "刷新", "en": "Refresh"},
    "New": {"zh": "新建", "en": "New"},
    "Save": {"zh": "保存", "en": "Save"},
    "Duplicate": {"zh": "复制副本", "en": "Duplicate"},
    "Delete": {"zh": "删除", "en": "Delete"},
    "Refresh config from selected topics": {"zh": "从已选 Topics 刷新配置", "en": "Refresh config from selected topics"},
    "Apply form -> YAML": {"zh": "应用表单 -> YAML", "en": "Apply form -> YAML"},
    "Reload form <- YAML": {"zh": "重载表单 <- YAML", "en": "Reload form <- YAML"},
    "Apply form to YAML ↓": {"zh": "表单写入 YAML ↓", "en": "Apply form to YAML ↓"},
    "Reload form from YAML ↑": {"zh": "从 YAML 刷新表单 ↑", "en": "Reload form from YAML ↑"},
    "Validate": {"zh": "校验", "en": "Validate"},
    "Environment": {"zh": "环境", "en": "Environment"},
    "Robot": {"zh": "机器人", "en": "Robot"},
    "Instruction": {"zh": "指令", "en": "Instruction"},
    "Recording / Image": {"zh": "采集 / 图像", "en": "Recording / Image"},
    "ROS Topics": {"zh": "ROS Topics", "en": "ROS Topics"},
    "AI Match Config": {"zh": "AI 匹配配置", "en": "AI Match Config"},
    "Dataset preview": {"zh": "数据集预览", "en": "Dataset preview"},
    "AI config preview": {"zh": "AI 配置预览", "en": "AI config preview"},
    "Default prompt": {"zh": "默认 Prompt", "en": "Default prompt"},
    "Replace dataset_config from AI preview": {"zh": "用 AI 预览替换 dataset_config", "en": "Replace dataset_config from AI preview"},
}


def normalize_language(language: str) -> str:
    return "zh" if str(language).lower().startswith("zh") else "en"


def text(value: str, language: str) -> str:
    key = _canonical_key(value)
    if key is None:
        return value
    return TEXTS[key].get(normalize_language(language), key)


def apply_i18n(root: QWidget, language: str) -> None:
    language = normalize_language(language)
    if isinstance(root, QMainWindow):
        root.setWindowTitle(text(root.windowTitle(), language))
        _translate_menu_bar(root.menuBar(), language)
    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        if isinstance(widget, QAbstractButton):
            widget.setText(text(widget.text(), language))
        elif isinstance(widget, QLabel):
            widget.setText(text(widget.text(), language))
        elif isinstance(widget, QGroupBox):
            widget.setTitle(text(widget.title(), language))
        elif isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                widget.setTabText(index, text(widget.tabText(index), language))
        elif isinstance(widget, QTableWidget):
            for column in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(column)
                if item is not None:
                    item.setText(text(item.text(), language))


def _translate_menu_bar(menu_bar: QMenuBar, language: str) -> None:
    for action in menu_bar.actions():
        _translate_action(action, language)


def _translate_action(action: QAction, language: str) -> None:
    action.setText(text(action.text(), language))
    menu = action.menu()
    if isinstance(menu, QMenu):
        menu.setTitle(text(menu.title(), language))
        for child in menu.actions():
            _translate_action(child, language)


def _canonical_key(value: str) -> str | None:
    clean = value.replace("&", "")
    if clean in TEXTS:
        return clean
    for key, translations in TEXTS.items():
        if clean in translations.values():
            return key
    return None
