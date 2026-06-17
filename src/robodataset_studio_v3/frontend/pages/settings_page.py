from __future__ import annotations

import yaml
from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class SettingsPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Settings", api, project)
        self.ai_enabled = QCheckBox("Enable AI")
        self.ai_base_url = QLineEdit()
        self.ai_api_key = QLineEdit()
        self.ai_api_key.setEchoMode(QLineEdit.Password)
        self.ai_model = QLineEdit()
        self.ai_timeout = QSpinBox()
        self.ai_timeout.setRange(5, 600)
        self.ai_timeout.setSuffix(" sec")
        self.language = QLineEdit()
        self.yaml_editor = self.output
        self.yaml_editor.setReadOnly(False)
        self.settings: dict = {}
        self._build_settings()
        self.load()

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
        ai_form.addRow("Default model", self.ai_model)
        ai_form.addRow("Timeout", self.ai_timeout)
        ai_form.addRow(QLabel("AI settings are stored locally and are not written into total_config.yaml."))

        general = QWidget()
        general_form = QFormLayout(general)
        general_form.addRow("Language", self.language)

        tabs = QTabWidget()
        tabs.addTab(general, "General")
        tabs.addTab(ai_widget, "AI")
        tabs.addTab(self.yaml_editor, "Advanced YAML")

        self.layout.addLayout(buttons)
        self.layout.addWidget(tabs)
        self.layout.addWidget(self.status)

    def load(self) -> None:
        try:
            result = self.api.get("/api/settings")
        except Exception as exc:
            self.show_error(exc)
            return
        self.settings = result if isinstance(result, dict) else {}
        ai = self.settings.get("ai", {}) if isinstance(self.settings.get("ai"), dict) else {}
        self.language.setText(str(self.settings.get("language", "en")))
        self.ai_enabled.setChecked(bool(ai.get("enabled", False)))
        self.ai_base_url.setText(str(ai.get("base_url", "")))
        self.ai_api_key.setText(str(ai.get("api_key", "")))
        self.ai_model.setText(str(ai.get("model", "")))
        self.ai_timeout.setValue(int(ai.get("timeout_sec") or 90))
        self.yaml_editor.setPlainText(yaml.safe_dump(self.settings, sort_keys=False, allow_unicode=True))
        self.status.setText("Settings loaded")

    def save(self) -> None:
        try:
            settings = yaml.safe_load(self.yaml_editor.toPlainText())
            if not isinstance(settings, dict):
                settings = {}
            settings["language"] = self.language.text().strip() or "en"
            settings.setdefault("ai", {})
            settings["ai"].update(
                {
                    "enabled": self.ai_enabled.isChecked(),
                    "base_url": self.ai_base_url.text().strip(),
                    "api_key": self.ai_api_key.text().strip(),
                    "model": self.ai_model.text().strip(),
                    "timeout_sec": int(self.ai_timeout.value()),
                }
            )
            saved = self.api.put("/api/settings", settings)
        except Exception as exc:
            self.show_error(exc)
            return
        self.settings = saved if isinstance(saved, dict) else settings
        self.yaml_editor.setPlainText(yaml.safe_dump(self.settings, sort_keys=False, allow_unicode=True))
        self.status.setText("Settings saved")
