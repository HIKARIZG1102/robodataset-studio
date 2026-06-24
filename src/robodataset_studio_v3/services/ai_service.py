from __future__ import annotations

import copy
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
        prompt_budget = context.get("prompt_budget", {}) if isinstance(context.get("prompt_budget"), dict) else {}
        char_budget = int(prompt_budget.get("char_budget") or os.environ.get("ROBODATASET_AI_PROMPT_CHAR_BUDGET", "120000"))
        prompt_context = {
            "selected_topics": selected_topics,
            "selected_topic_probes": selected_topic_probes,
            "dataset_schema_notes": context.get("dataset_schema_notes", ""),
            "selection_policy": context.get("selection_policy", "Use only selected topics."),
            "prompt_budget": prompt_budget,
        }
        prompt = self._build_config_prompt(current_total_config, dataset_config, prompt_context)
        original_prompt_chars = len(prompt)
        over_budget = original_prompt_chars > char_budget
        compacted = False
        truncated = False
        if len(prompt) > char_budget:
            compacted = True
            compact_context = self._compact_prompt_context(prompt_context)
            prompt = self._build_config_prompt(current_total_config, dataset_config, compact_context)
        if len(prompt) > char_budget:
            compacted = True
            compact_total = copy.deepcopy(current_total_config)
            if isinstance(compact_total, dict) and "dataset_config" in compact_total:
                compact_total["dataset_config"] = "omitted here because Current dataset_config YAML is provided separately below"
            prompt = self._build_config_prompt(compact_total, dataset_config, self._compact_prompt_context(prompt_context, aggressive=True))
        if len(prompt) > char_budget:
            truncated = True
            prompt = prompt[:char_budget] + "\n...[prompt truncated to configured AI prompt_char_budget]..."
        result = {
            "prompt": prompt,
            "prompt_chars": len(prompt),
            "original_prompt_chars": original_prompt_chars,
            "prompt_char_budget": char_budget,
            "over_budget": over_budget,
            "compacted": compacted,
            "truncated": truncated,
        }
        task = task_service.run_instant("ai_config_prompt", "generated AI config prompt", result)
        return {"task_id": task.task_id, "result": result}

    def _build_config_prompt(self, current_total_config: dict[str, Any], dataset_config: dict[str, Any], prompt_context: dict[str, Any]) -> str:
        return "\n".join(
            [
                "You are helping generate the dataset_config section for RoboDataset Studio.",
                "Return valid YAML only.",
                "Return only the dataset_config mapping. Do not wrap it under total_config.",
                "Do not include project name or project version: those belong to the project, not the reusable config.",
                "Use only selected ROS topics, topic info, echo samples, and hz checks to fill cameras/streams/state/action.",
                "Selected/listener ROS topics belong to total_config.ros, not dataset_config. Do not include a ros section in the returned dataset_config.",
                "total_config.ros.discovery_snapshot is only a UI/monitor snapshot. Do not record topics from discovery_snapshot unless they also appear in selected_topics.",
                "Prefer selected_topic_probes.*.structured over stdout_summary when both are present; structured fields are intentionally lossless for config-relevant values.",
                "For sensor_msgs/msg/Image with rgb8/bgr8 encoding, set stream shape as [height, width, 3]. For mono/depth images, preserve the observed height and width and do not invent RGB channels.",
                "Classify depth or non-RGB image topics as extension streams with calvin_key null unless the user explicitly promotes them to a core key.",
                "Map RGB/color image topics to CALVIN-like core observation keys such as rgb_static, rgb_wrist, rgb_overhead, and extra rgb_* tracks.",
                "For sensor_msgs/msg/JointState, use structured.joint_order, joint_count, position_dim, velocity_dim, and effort_dim to fill robot/state/action dimensions.",
                "For multiple JointState topics, create one state.keys entry per selected topic with stable names; use action.source_state_key to identify which state derives rel_actions/actions.",
                "Every selected topic that should be recorded must appear in streams, state.keys, or action source fields.",
                "Fill dataset.core_schema so it exactly describes streams/state/action fields that collection will write into each NPZ/HDF5 dataset.",
                "Keep metadata extension keys separate from CALVIN-compatible core fields. Include collection_config, task_info, environment_info, robot_info, and stream_schema metadata extensions.",
                "Include or update dataset.recording_estimate from recording settings. Use 0 for manual/open-ended unknown sample counts.",
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

    def _compact_prompt_context(self, prompt_context: dict[str, Any], aggressive: bool = False) -> dict[str, Any]:
        compact = copy.deepcopy(prompt_context)
        probes = compact.get("selected_topic_probes", [])
        if not isinstance(probes, list):
            return compact
        for probe in probes:
            if not isinstance(probe, dict):
                continue
            for key in ["topic_info", "echo_once", "hz"]:
                check = probe.get(key)
                if not isinstance(check, dict):
                    continue
                has_structured = isinstance(check.get("structured"), dict) and bool(check.get("structured"))
                if has_structured:
                    check.pop("stdout_summary", None)
                elif isinstance(check.get("stdout_summary"), str):
                    limit = 800 if aggressive else 2000
                    check["stdout_summary"] = self._truncate_text(check["stdout_summary"], limit)
                if isinstance(check.get("error_summary"), str):
                    check["error_summary"] = self._truncate_text(check["error_summary"], 800 if aggressive else 1600)
        return compact

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        keep = max(int((limit - 80) / 2), 1)
        return f"{text[:keep]}\n...[truncated {len(text) - keep * 2} chars]...\n{text[-keep:]}"

    def _safe_total_config(self, config: dict[str, Any]) -> dict[str, Any]:
        safe = dict(config)
        for key in ["upload", "config_meta", "paths", "collection", "review", "convert", "ui", "ai"]:
            safe.pop(key, None)
        if isinstance(safe.get("dataset_config"), dict):
            safe["dataset_config"] = self._safe_dataset_config(safe["dataset_config"])
        return safe

    def _safe_dataset_config(self, dataset_config: dict[str, Any]) -> dict[str, Any]:
        safe = dict(dataset_config)
        safe.pop("ros", None)
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
