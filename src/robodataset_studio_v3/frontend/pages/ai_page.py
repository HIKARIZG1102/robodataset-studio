from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class AiPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("AI Assist", api, project)
        self.base_url = QLineEdit()
        self.model = QLineEdit()
        self.prompt = QLineEdit()
        form = QFormLayout()
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)
        form.addRow("Prompt", self.prompt)
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
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.finish_layout()

    def models(self) -> None:
        self._post("/api/ai/models", {"base_url": self.base_url.text().strip()}, "Model request complete")

    def config_prompt(self) -> None:
        dataset_config = {}
        if self.project is not None:
            try:
                dataset_config = self.api.get_dataset_config(self.project.key)
            except Exception:
                dataset_config = {}
        self._post("/api/ai/config-prompt", {"dataset_config": dataset_config, "ros_context": {}}, "Config prompt generated")

    def review_prompt(self) -> None:
        self._post("/api/ai/review-prompt", {"review_summary": {}}, "Review prompt generated")

    def send(self) -> None:
        self._post(
            "/api/ai/send",
            {
                "prompt": self.prompt.text().strip(),
                "kind": "ai",
                "base_url": self.base_url.text().strip(),
                "model": self.model.text().strip(),
            },
            "AI request complete",
        )

    def _post(self, path: str, payload: dict, status: str) -> None:
        try:
            self.show_result(self.api.post(path, payload), status)
        except Exception as exc:
            self.show_error(exc)
