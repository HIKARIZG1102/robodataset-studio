from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from robodataset_studio_v3.backend.routers import ai, config, convert, health, projects, recording, review, ros, settings, tasks, upload


def create_app() -> FastAPI:
    app = FastAPI(title="RoboDataset Studio V3 Backend", version="0.1.0")
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(ros.router, prefix="/api/ros", tags=["ros"])
    app.include_router(recording.router, prefix="/api/recording", tags=["recording"])
    app.include_router(review.router, prefix="/api/review", tags=["review"])
    app.include_router(convert.router, prefix="/api/convert", tags=["convert"])
    app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
    app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    return app


app = create_app()


def main() -> None:
    host = os.environ.get("ROBODATASET_V3_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("ROBODATASET_V3_BACKEND_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
