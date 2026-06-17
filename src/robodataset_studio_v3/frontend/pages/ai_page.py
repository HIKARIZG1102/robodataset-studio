from __future__ import annotations

import json

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSplitter, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class AiPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("AI Assist", api, project)
        self.prompt = QPlainTextEdit()
        self.response = QPlainTextEdit()
        self.response.setReadOnly(True)
        self._build()

    def _build(self) -> None:
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
        self.layout.addWidget(QLabel("AI base URL, API key, model, and timeout are configured in Settings."))
        self.layout.addLayout(buttons)
        self.layout.addWidget(splitter)
        self.finish_layout()

    def models(self) -> None:
        self.status.setText("Requesting models...")
        self.run_async(self.models_with_settings, self._finish_models)

    def models_with_settings(self) -> object:
        settings = self.api.get("/api/settings", timeout=5.0)
        ai = settings.get("ai", {}) if isinstance(settings, dict) and isinstance(settings.get("ai"), dict) else {}
        return self.api.post("/api/ai/models", {"base_url": str(ai.get("base_url", "")), "api_key": str(ai.get("api_key", ""))}, timeout=30.0)

    def _finish_models(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        data = result if isinstance(result, dict) else {}
        payload = data.get("result", data) if isinstance(data.get("result", data), dict) else {}
        models = payload.get("models", []) if isinstance(payload, dict) else []
        self.response.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self.status.setText("Models loaded" if models else "No available models")

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
        self.run_async(self.send_with_settings, self._finish_send, self.prompt.toPlainText().strip())

    def send_with_settings(self, prompt: str) -> object:
        settings = self.api.get("/api/settings", timeout=5.0)
        ai = settings.get("ai", {}) if isinstance(settings, dict) and isinstance(settings.get("ai"), dict) else {}
        if not ai.get("enabled"):
            raise RuntimeError("Enable AI in Settings first.")
        return self.api.post(
            "/api/ai/send",
            {
                "prompt": prompt,
                "kind": "ai",
                "base_url": str(ai.get("base_url", "")),
                "model": str(ai.get("model", "")),
                "api_key": str(ai.get("api_key", "")),
            },
            timeout=float(ai.get("timeout_sec") or 120),
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
