from __future__ import annotations

from robodataset_studio_v3.models.config import CollectionConfigDraft, ConfigPreview


class ConfigService:
    def preview(self, config: CollectionConfigDraft) -> ConfigPreview:
        stream_count = len(config.streams)
        image_count = sum(1 for stream in config.streams if "Image" in str(stream.get("message_type", "")))
        summary = (
            f"project={config.project.get('name', '')} "
            f"streams={stream_count} image_streams={image_count}"
        )
        warnings = []
        if not config.project.get("name"):
            warnings.append("project.name is empty")
        if not config.streams:
            warnings.append("no streams selected")
        return ConfigPreview(summary=summary, warnings=warnings)
