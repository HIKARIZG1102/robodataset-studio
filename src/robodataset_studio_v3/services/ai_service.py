from __future__ import annotations

from typing import Any

from robodataset_studio_v3.services.task_service import task_service


class AiService:
    def config_prompt(self, dataset_config: dict[str, Any], ros_context: dict[str, Any] | None = None) -> dict[str, Any]:
        prompt = "\n".join(
            [
                "You are helping generate a RoboDataset dataset_config.yaml.",
                "Return valid YAML only unless asked for explanation.",
                "Use selected ROS topics, topic info, echo samples, and hz checks to fill streams/state/action.",
                "Do not include upload server settings, API keys, passwords, or UI state.",
                "",
                "Current dataset_config:",
                str(dataset_config),
                "",
                "ROS context:",
                str(ros_context or {}),
            ]
        )
        result = {"prompt": prompt}
        task = task_service.run_instant("ai_config_prompt", "generated AI config prompt", result)
        return {"task_id": task.task_id, "result": result}

    def review_prompt(self, review_summary: dict[str, Any]) -> dict[str, Any]:
        prompt = "\n".join(
            [
                "Review this robot dataset quality summary.",
                "Find episodes with low motion, too few samples, missing fields, abnormal images, or schema mismatch.",
                "Return specific episode ids and reasons.",
                "",
                str(review_summary),
            ]
        )
        result = {"prompt": prompt}
        task = task_service.run_instant("ai_review_prompt", "generated AI review prompt", result)
        return {"task_id": task.task_id, "result": result}

    def models(self, base_url: str = "") -> dict[str, Any]:
        result = {"base_url": base_url, "models": [], "message": "model discovery hook is ready; provider call is not configured"}
        task = task_service.run_instant("ai_models", "checked AI model list", result)
        return {"task_id": task.task_id, "result": result}

    def send(self, prompt: str, kind: str = "ai") -> dict[str, Any]:
        result = {
            "kind": kind,
            "response": "",
            "message": "AI send hook is ready; configure provider settings before enabling remote requests",
            "prompt_chars": len(prompt),
        }
        task = task_service.run_instant(kind, "AI request prepared", result)
        return {"task_id": task.task_id, "result": result}


ai_service = AiService()
