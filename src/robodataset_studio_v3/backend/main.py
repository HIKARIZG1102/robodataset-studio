from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from robodataset_studio_v3.backend.routers import config, health, projects, tasks


def create_app() -> FastAPI:
    app = FastAPI(title="RoboDataset Studio V3 Backend", version="0.1.0")
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    return app


app = create_app()


def main() -> None:
    host = os.environ.get("ROBODATASET_V3_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("ROBODATASET_V3_BACKEND_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
