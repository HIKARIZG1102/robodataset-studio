from __future__ import annotations

import os
from typing import Any

import httpx

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
        task = task_service.create_task("ai_models", "checking AI models")
        api_key = os.environ.get("ROBOT_DATA_AI_API_KEY", "")
        if not base_url:
            result = {"base_url": base_url, "models": [], "error": "base_url is empty"}
            task_service.fail_task(task.task_id, message="model discovery failed", error=result["error"])
            return {"task_id": task.task_id, "result": result}
        try:
            url = base_url.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            response = httpx.get(url, headers=headers, timeout=20.0)
            response.raise_for_status()
            payload = response.json()
            models = payload.get("data", payload if isinstance(payload, list) else [])
            result = {"base_url": base_url, "models": models}
            task_service.complete_task(task.task_id, message="model discovery finished", result=result)
        except Exception as exc:
            result = {"base_url": base_url, "models": [], "error": str(exc)}
            task_service.fail_task(task.task_id, message="model discovery failed", error=str(exc))
        return {"task_id": task.task_id, "result": result}

    def send(self, prompt: str, kind: str = "ai", base_url: str = "", model: str = "") -> dict[str, Any]:
        task = task_service.create_task(kind, "AI request started")
        api_key = os.environ.get("ROBOT_DATA_AI_API_KEY", "")
        if not base_url or not model:
            result = {"kind": kind, "response": "", "error": "base_url and model are required", "prompt_chars": len(prompt)}
            task_service.fail_task(task.task_id, message="AI request failed", error=result["error"])
            return {"task_id": task.task_id, "result": result}
        try:
            url = base_url.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            response = httpx.post(
                url,
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
                timeout=90.0,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            result = {"kind": kind, "response": content, "raw": payload, "prompt_chars": len(prompt)}
            task_service.complete_task(task.task_id, message="AI request finished", result=result)
        except Exception as exc:
            result = {"kind": kind, "response": "", "error": str(exc), "prompt_chars": len(prompt)}
            task_service.fail_task(task.task_id, message="AI request failed", error=str(exc))
        return {"task_id": task.task_id, "result": result}


ai_service = AiService()
