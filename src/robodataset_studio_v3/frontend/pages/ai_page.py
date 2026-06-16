from __future__ import annotations

import json

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class AiPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("AI Assist", api, project)
        self.base_url = QLineEdit()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.prompt = QPlainTextEdit()
        self.response = QPlainTextEdit()
        self.response.setReadOnly(True)
        self._build()

    def _build(self) -> None:
        form = QFormLayout()
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)
        buttons = QHBoxLayout()
        for label, handler in [
            ("List Models", self.models),
            ("Default Config Prompt", self.config_prompt),
            ("Default Review Prompt", self.review_prompt),
            ("Send", self.send),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        splitter = QSplitter()
        prompt_box = QWidget()
        prompt_layout = QFormLayout(prompt_box)
        prompt_layout.addRow("AI Prompt", self.prompt)
        response_box = QWidget()
        response_layout = QFormLayout(response_box)
        response_layout.addRow("AI Response", self.response)
        splitter.addWidget(prompt_box)
        splitter.addWidget(response_box)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.layout.addWidget(splitter)
        self.finish_layout()

    def models(self) -> None:
        self.status.setText("Requesting models...")
        self.run_async(self.api.post, self._finish_models, "/api/ai/models", {"base_url": self.base_url.text().strip()}, timeout=30.0)

    def _finish_models(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        data = result if isinstance(result, dict) else {}
        payload = data.get("result", data) if isinstance(data.get("result", data), dict) else {}
        models = payload.get("models", []) if isinstance(payload, dict) else []
        current = self.model.currentText().strip()
        self.model.clear()
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    name = str(item.get("id") or item.get("name") or "")
                else:
                    name = str(item)
                if name:
                    self.model.addItem(name)
        if current:
            self.model.setCurrentText(current)
        self.response.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self.status.setText("Models loaded" if self.model.count() else "No available models")

    def config_prompt(self) -> None:
        dataset_config = {}
        ros_context = {}
        if self.project is not None:
            try:
                dataset_config = self.api.get_dataset_config(self.project.key)
                ros_context = dataset_config.get("ros", {}) if isinstance(dataset_config.get("ros"), dict) else {}
            except Exception:
                dataset_config = {}
        self.status.setText("Generating config prompt...")
        self.run_async(
            self.api.post,
            self._finish_prompt,
            "/api/ai/config-prompt",
            {"dataset_config": dataset_config, "ros_context": ros_context},
            timeout=30.0,
        )

    def review_prompt(self) -> None:
        self.status.setText("Generating review prompt...")
        self.run_async(self.api.post, self._finish_prompt, "/api/ai/review-prompt", {"review_summary": {}}, timeout=30.0)

    def _finish_prompt(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        data = result if isinstance(result, dict) else {}
        payload = data.get("result", data) if isinstance(data.get("result", data), dict) else {}
        text = str(payload.get("prompt", "")) if isinstance(payload, dict) else ""
        self.prompt.setPlainText(text)
        self.response.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self.status.setText("Prompt generated; review it before sending")

    def send(self) -> None:
        self.status.setText("Sending AI request...")
        self.run_async(
            self.api.post,
            self._finish_send,
            "/api/ai/send",
            {
                "prompt": self.prompt.toPlainText().strip(),
                "kind": "ai",
                "base_url": self.base_url.text().strip(),
                "model": self.model.currentText().strip(),
            },
            timeout=120.0,
        )

    def _finish_send(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        data = result if isinstance(result, dict) else {}
        payload = data.get("result", data) if isinstance(data.get("result", data), dict) else {}
        response = str(payload.get("response", "")) if isinstance(payload, dict) else ""
        self.response.setPlainText(response or json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self.status.setText("AI request complete")
