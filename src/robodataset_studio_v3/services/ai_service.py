from __future__ import annotations

import os
from typing import Any

import httpx
import yaml

from robodataset_studio_v3.services.task_service import task_service


class AiService:
    def config_prompt(self, dataset_config: dict[str, Any], ros_context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = ros_context or {}
        selected_topics = context.get("selected_topics", []) if isinstance(context.get("selected_topics"), list) else []
        selected_topic_probes = context.get("selected_topic_probes", []) if isinstance(context.get("selected_topic_probes"), list) else []
        current_total_config = self._safe_total_config(context.get("current_total_config", {}) if isinstance(context.get("current_total_config"), dict) else {})
        dataset_config = self._safe_dataset_config(dataset_config)
        prompt_context = {
            "selected_topics": selected_topics,
            "selected_topic_probes": selected_topic_probes,
            "selection_policy": context.get("selection_policy", "Use only selected topics."),
        }
        prompt = "\n".join(
            [
                "You are helping generate the dataset_config section for RoboDataset Studio.",
                "Return valid YAML only.",
                "Return only the dataset_config mapping. Do not wrap it under total_config.",
                "Do not include project name or project version: those belong to the project, not the reusable config.",
                "Use only selected ROS topics, topic info, echo samples, and hz checks to fill cameras/streams/state/action.",
                "Do not use unselected ROS graph topics. If a topic is not listed in selected_topics, ignore it.",
                "If selected_topics is empty, return the current config unchanged and add no streams.",
                "Keep listener-only runtime behavior and do not enable robot command publishing unless explicitly requested.",
                "Do not include upload settings, AI API keys, passwords, config_meta, paths, collection, review, convert, or UI state.",
                "Preserve environment, instruction, recording, and dataset values unless selected topic evidence requires a dataset mapping change.",
                "You may infer robot fields from selected topic names and message samples, e.g. /wx250s/... implies a wx250s/WidowX style robot, but do not invent command publishing.",
                "If current_total_config contains useful form values, fold only its dataset_config-relevant values into the returned dataset_config.",
                "",
                "Current safe total_config YAML:",
                yaml.safe_dump(current_total_config, sort_keys=False, allow_unicode=True),
                "",
                "Current dataset_config YAML:",
                yaml.safe_dump(dataset_config, sort_keys=False, allow_unicode=True),
                "",
                "Selected ROS context YAML:",
                yaml.safe_dump(prompt_context, sort_keys=False, allow_unicode=True),
            ]
        )
        result = {"prompt": prompt}
        task = task_service.run_instant("ai_config_prompt", "generated AI config prompt", result)
        return {"task_id": task.task_id, "result": result}

    def _safe_total_config(self, config: dict[str, Any]) -> dict[str, Any]:
        safe = dict(config)
        for key in ["upload", "config_meta", "paths", "collection", "review", "convert", "ui", "ai"]:
            safe.pop(key, None)
        if isinstance(safe.get("dataset_config"), dict):
            safe["dataset_config"] = self._safe_dataset_config(safe["dataset_config"])
        return safe

    def _safe_dataset_config(self, dataset_config: dict[str, Any]) -> dict[str, Any]:
        safe = dict(dataset_config)
        ros = dict(safe.get("ros", {})) if isinstance(safe.get("ros"), dict) else {}
        ros.pop("discovery_snapshot", None)
        safe["ros"] = ros
        return safe

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

    def models(self, base_url: str = "", api_key: str = "") -> dict[str, Any]:
        task = task_service.create_task("ai_models", "checking AI models")
        api_key = api_key or os.environ.get("ROBOT_DATA_AI_API_KEY", "")
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

    def send(self, prompt: str, kind: str = "ai", base_url: str = "", model: str = "", api_key: str = "") -> dict[str, Any]:
        task = task_service.create_task(kind, "AI request started")
        api_key = api_key or os.environ.get("ROBOT_DATA_AI_API_KEY", "")
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
