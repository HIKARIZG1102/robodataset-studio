from __future__ import annotations

import yaml
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class SettingsPage(BasePage):
    settingsSaved = Signal(object)

    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Settings", api, project)
        self.ai_enabled = QCheckBox("Enable AI")
        self.ai_base_url = QLineEdit()
        self.ai_api_key = QLineEdit()
        self.ai_api_key.setEchoMode(QLineEdit.Password)
        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_timeout = QSpinBox()
        self.ai_timeout.setRange(5, 600)
        self.ai_timeout.setSuffix(" sec")
        self.ai_prompt_budget = QSpinBox()
        self.ai_prompt_budget.setRange(20000, 1000000)
        self.ai_prompt_budget.setSingleStep(10000)
        self.ai_prompt_budget.setSuffix(" chars")
        self.ai_probe_budget = QSpinBox()
        self.ai_probe_budget.setRange(2000, 100000)
        self.ai_probe_budget.setSingleStep(1000)
        self.ai_probe_budget.setSuffix(" chars")
        self.model_status = QLabel("")
        self.refresh_models_button: QPushButton | None = None
        self.language = QComboBox()
        self.language.addItem("English", "en")
        self.language.addItem("中文", "zh")
        self.tabs = QTabWidget()
        self.environment_summary = QLabel("")
        self.environment_summary.setWordWrap(True)
        self.environment_issues = QPlainTextEdit()
        self.environment_issues.setReadOnly(True)
        self.environment_issues.setMaximumHeight(180)
        self.environment_detail = QPlainTextEdit()
        self.environment_detail.setReadOnly(True)
        self.yaml_editor = self.output
        self.yaml_editor.setReadOnly(False)
        self.settings: dict = {}
        self._build_settings()
        self.load()
        self._connect_auto_save()

    def _build_settings(self) -> None:
        buttons = QHBoxLayout()
        load = QPushButton("Load Settings")
        save = QPushButton("Save Settings")
        load.clicked.connect(self.load)
        save.clicked.connect(self.save)
        buttons.addWidget(load)
        buttons.addWidget(save)
        buttons.addStretch(1)

        ai_widget = QWidget()
        ai_form = QFormLayout(ai_widget)
        ai_form.addRow(self.ai_enabled)
        ai_form.addRow("OpenAI-compatible base URL", self.ai_base_url)
        ai_form.addRow("API key", self.ai_api_key)
        model_row = QHBoxLayout()
        refresh_models = QPushButton("Refresh models")
        self.refresh_models_button = refresh_models
        refresh_models.clicked.connect(self.refresh_models)
        model_row.addWidget(self.ai_model, 1)
        model_row.addWidget(refresh_models)
        ai_form.addRow("Default model", model_row)
        ai_form.addRow("Timeout", self.ai_timeout)
        ai_form.addRow("Prompt budget", self.ai_prompt_budget)
        ai_form.addRow("Probe stdout budget", self.ai_probe_budget)
        ai_form.addRow("Model status", self.model_status)
        ai_form.addRow(QLabel("AI settings are stored locally and are not written into total_config.yaml."))

        general = QWidget()
        general_form = QFormLayout(general)
        general_form.addRow("Language", self.language)

        self.environment_widget = QWidget()
        environment_layout = QFormLayout(self.environment_widget)
        refresh_environment = QPushButton("Refresh Environment Diagnostics")
        refresh_environment.clicked.connect(self.refresh_environment)
        environment_layout.addRow(refresh_environment)
        environment_layout.addRow("Summary", self.environment_summary)
        environment_layout.addRow("Issues", self.environment_issues)
        environment_layout.addRow("Details", self.environment_detail)

        self.tabs.addTab(general, "General")
        self.tabs.addTab(ai_widget, "AI")
        self.tabs.addTab(self.environment_widget, "Environment")
        self.tabs.addTab(self.yaml_editor, "Advanced YAML")

        self.layout.addLayout(buttons)
        self.layout.addWidget(self.tabs)
        self.layout.addWidget(self.status)

    def load(self) -> None:
        try:
            result = self.api.get("/api/settings")
        except Exception as exc:
            self.show_error(exc)
            return
        self.settings = result if isinstance(result, dict) else {}
        ai = self.settings.get("ai", {}) if isinstance(self.settings.get("ai"), dict) else {}
        self._set_language(str(self.settings.get("language", "en")))
        self.ai_enabled.setChecked(bool(ai.get("enabled", False)))
        self.ai_base_url.setText(str(ai.get("base_url", "")))
        self.ai_api_key.setText(str(ai.get("api_key", "")))
        self._set_model_text(str(ai.get("model", "")))
        self.ai_timeout.setValue(int(ai.get("timeout_sec") or 90))
        self.ai_prompt_budget.setValue(int(ai.get("prompt_char_budget") or 120000))
        self.ai_probe_budget.setValue(int(ai.get("probe_stdout_budget") or 12000))
        self.yaml_editor.setPlainText(yaml.safe_dump(self.settings, sort_keys=False, allow_unicode=True))
        self.status.setText("Settings loaded")
        self.refresh_environment()

    def save(self) -> None:
        try:
            settings = yaml.safe_load(self.yaml_editor.toPlainText())
            if not isinstance(settings, dict):
                settings = {}
            settings["language"] = str(self.language.currentData() or "en")
            settings.setdefault("ai", {})
            settings["ai"].update(
                {
                    "enabled": self.ai_enabled.isChecked(),
                    "base_url": self.ai_base_url.text().strip(),
                    "api_key": self.ai_api_key.text().strip(),
                    "model": self.ai_model.currentText().strip(),
                    "timeout_sec": int(self.ai_timeout.value()),
                    "prompt_char_budget": int(self.ai_prompt_budget.value()),
                    "probe_stdout_budget": int(self.ai_probe_budget.value()),
                }
            )
            saved = self.api.put("/api/settings", settings)
        except Exception as exc:
            self.show_error(exc)
            return
        self.settings = saved if isinstance(saved, dict) else settings
        self.yaml_editor.setPlainText(yaml.safe_dump(self.settings, sort_keys=False, allow_unicode=True))
        self.status.setText("Settings saved")
        self.settingsSaved.emit(self.settings)

    def refresh_models(self) -> None:
        self.save()
        base_url = self.ai_base_url.text().strip()
        api_key = self.ai_api_key.text().strip()
        if not base_url:
            self.model_status.setText("base URL required")
            return
        if not api_key:
            self.model_status.setText("API key empty; trying model list without Authorization header")
        else:
            self.model_status.setText(f"checking models from {base_url.rstrip('/')}/models ...")
        if self.refresh_models_button is not None:
            self.refresh_models_button.setEnabled(False)
            self.refresh_models_button.setText("Checking...")
        self.status.setText("Refreshing AI model list...")
        self.run_async(
            self.api.post,
            self.finish_model_refresh,
            "/api/ai/models",
            {"base_url": base_url, "api_key": api_key},
            timeout=35.0,
        )

    def refresh_environment(self) -> None:
        self.environment_summary.setText("Loading environment diagnostics...")
        self.environment_issues.setPlainText("")
        self.environment_detail.setPlainText("")
        self.run_async(self.api.get, self.finish_environment_refresh, "/api/environment/diagnostics", timeout=20.0)

    def finish_environment_refresh(self, result: object, error: object) -> None:
        if error is not None:
            self.environment_summary.setText(f"Environment diagnostics failed: {error}")
            return
        payload = result if isinstance(result, dict) else {}
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        issues = payload.get("issues", []) if isinstance(payload.get("issues"), list) else []
        self.environment_summary.setText(
            " | ".join(
                [
                    f"python={summary.get('python', '-')}",
                    f"rmw={summary.get('selected_rmw', '-')}",
                    f"topics={summary.get('topic_count', '-')}",
                    f"issues={summary.get('issue_count', len(issues))}",
                    f"ros_setup={summary.get('ros_setup', '-')}",
                ]
            )
        )
        if issues:
            lines = []
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                lines.append(
                    f"[{issue.get('severity', 'warning')}] {issue.get('name', '')}\n"
                    f"  detail: {issue.get('detail', '')}\n"
                    f"  impact: {issue.get('impact', '')}"
                )
            self.environment_issues.setPlainText("\n\n".join(lines))
        else:
            self.environment_issues.setPlainText("No blocking environment issues detected.")
        self.environment_detail.setPlainText(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        self.status.setText("Environment diagnostics refreshed")

    def show_environment(self) -> None:
        index = self.tabs.indexOf(self.environment_widget)
        if index >= 0:
            self.tabs.setCurrentIndex(index)
        self.refresh_environment()

    def finish_model_refresh(self, result: object, error: object) -> None:
        if self.refresh_models_button is not None:
            self.refresh_models_button.setEnabled(True)
            self.refresh_models_button.setText("Refresh models")
        if error is not None:
            self.model_status.setText(f"model list failed: {error}")
            self.status.setText("AI model refresh failed")
            return
        payload = result.get("result", result) if isinstance(result, dict) else {}
        models = payload.get("models", []) if isinstance(payload, dict) else []
        model_ids: list[str] = []
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict) and item.get("id"):
                    model_ids.append(str(item.get("id")))
                elif isinstance(item, str):
                    model_ids.append(item)
        model_ids = list(dict.fromkeys(model_ids))
        current = self.ai_model.currentText().strip()
        self.ai_model.blockSignals(True)
        self.ai_model.clear()
        if model_ids:
            self.ai_model.addItems(model_ids)
            self.ai_model.setCurrentText(current if current in model_ids else model_ids[0])
            selected = self.ai_model.currentText().strip()
            self.model_status.setText(f"{len(model_ids)} model(s) available; selected {selected}")
            self.status.setText("AI model list refreshed")
        else:
            self.ai_model.setEditText(current)
            self.model_status.setText(str(payload.get("error") or "no available models") if isinstance(payload, dict) else "no available models")
            self.status.setText("AI model refresh returned no models")
        self.ai_model.blockSignals(False)
        self.save()

    def _set_model_text(self, text: str) -> None:
        if text and self.ai_model.findText(text) < 0:
            self.ai_model.addItem(text)
        self.ai_model.setCurrentText(text)

    def _set_language(self, language: str) -> None:
        data = "zh" if language.lower().startswith("zh") else "en"
        index = self.language.findData(data)
        if index >= 0:
            self.language.setCurrentIndex(index)

    def _connect_auto_save(self) -> None:
        self.ai_enabled.toggled.connect(lambda _checked: self.save())
        self.ai_base_url.editingFinished.connect(self.save)
        self.ai_api_key.editingFinished.connect(self.save)
        self.ai_model.currentTextChanged.connect(lambda _text: self.save())
        self.ai_timeout.valueChanged.connect(lambda _value: self.save())
        self.ai_prompt_budget.valueChanged.connect(lambda _value: self.save())
        self.ai_probe_budget.valueChanged.connect(lambda _value: self.save())
        self.language.currentIndexChanged.connect(lambda _index: self.save())
