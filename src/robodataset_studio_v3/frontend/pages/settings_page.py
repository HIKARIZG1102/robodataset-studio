from __future__ import annotations

import yaml
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class SettingsPage(BasePage):
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
        self.model_status = QLabel("")
        self.language = QLineEdit()
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
        refresh_models.clicked.connect(self.refresh_models)
        model_row.addWidget(self.ai_model, 1)
        model_row.addWidget(refresh_models)
        ai_form.addRow("Default model", model_row)
        ai_form.addRow("Timeout", self.ai_timeout)
        ai_form.addRow("Model status", self.model_status)
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
        self._set_model_text(str(ai.get("model", "")))
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
                    "model": self.ai_model.currentText().strip(),
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

    def refresh_models(self) -> None:
        self.save()
        base_url = self.ai_base_url.text().strip()
        api_key = self.ai_api_key.text().strip()
        if not base_url or not api_key:
            self.model_status.setText("base URL and API key required")
            return
        self.model_status.setText("loading models...")
        self.run_async(
            self.api.post,
            self.finish_model_refresh,
            "/api/ai/models",
            {"base_url": base_url, "api_key": api_key},
            timeout=30.0,
        )

    def finish_model_refresh(self, result: object, error: object) -> None:
        if error is not None:
            self.model_status.setText(f"model list failed: {error}")
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
            self.model_status.setText(f"{len(model_ids)} model(s) available")
        else:
            self.ai_model.setEditText(current)
            self.model_status.setText(str(payload.get("error") or "no available models") if isinstance(payload, dict) else "no available models")
        self.ai_model.blockSignals(False)
        self.save()

    def _set_model_text(self, text: str) -> None:
        if text and self.ai_model.findText(text) < 0:
            self.ai_model.addItem(text)
        self.ai_model.setCurrentText(text)

    def _connect_auto_save(self) -> None:
        self.ai_enabled.toggled.connect(lambda _checked: self.save())
        self.ai_base_url.editingFinished.connect(self.save)
        self.ai_api_key.editingFinished.connect(self.save)
        self.ai_model.currentTextChanged.connect(lambda _text: self.save())
        self.ai_timeout.valueChanged.connect(lambda _value: self.save())
        self.language.editingFinished.connect(self.save)
