"""The viewer's API, and the built frontend from the same origin.

Read-only over what the pipeline has built: the weekly picks and their transcripts in Postgres,
transcript·lab's Chroma chunks, the ingest log, MLflow runs and the Supadata balance.

Run it: `uv run rt serve` (127.0.0.1:8089); in development also `cd frontend && npm run dev`
(127.0.0.1:5178, proxying /api and /healthz here).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rotation_tracker.config import ROOT
from rotation_tracker.serving.store import READ_TOPICS

DIST = ROOT / "frontend" / "dist"
VIDEO_ID = r"^[A-Za-z0-9_-]{11}$"


class Reader(Protocol):
    def health(self) -> dict[str, Any]: ...
    def overview(self) -> dict[str, Any]: ...
    def weeks(self) -> list[dict[str, Any]]: ...
    def week(self, video_id: str) -> dict[str, Any] | None: ...
    def chunks(self, video_id: str) -> list[dict[str, Any]]: ...
    def search(self, q: str, topics: list[str], order: str, limit: int) -> dict[str, Any]: ...
    def chart(self, quarter: date | None) -> dict[str, Any]: ...
    def pipeline(self) -> dict[str, Any]: ...


def create_app(store: Reader | None = None, dist: Path = DIST) -> FastAPI:
    if store is None:
        from rotation_tracker.serving.store import Store

        store = Store()
    st: Reader = store
    app = FastAPI(
        title="rotation-tracker viewer",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return st.health()

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        return st.overview()

    @app.get("/api/weeks")
    def weeks() -> list[dict[str, Any]]:
        return st.weeks()

    @app.get("/api/weeks/{video_id}")
    def week(video_id: str = PathParam(pattern=VIDEO_ID)) -> dict[str, Any]:
        found = st.week(video_id)
        if found is None:
            raise HTTPException(404, f"{video_id} is not a weekly pick")
        return found

    @app.get("/api/weeks/{video_id}/chunks")
    def chunks(video_id: str = PathParam(pattern=VIDEO_ID)) -> list[dict[str, Any]]:
        return st.chunks(video_id)

    @app.get("/api/search")
    def search(
        q: str = "",
        topics: str = ",".join(READ_TOPICS),
        order: Literal["recent", "rank"] = "recent",
        limit: int = 60,
    ) -> dict[str, Any]:
        wanted = [t for t in topics.split(",") if t]
        return st.search(q[:200], wanted, order, max(1, min(limit, 200)))

    @app.get("/api/chart")
    def chart(quarter: date | None = None) -> dict[str, Any]:
        return st.chart(quarter)

    @app.get("/api/pipeline")
    def pipeline() -> dict[str, Any]:
        return st.pipeline()

    # ---- the built frontend ------------------------------------------------------------
    if (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404, f"no route /{path}")
            f = dist / path
            if path and f.is_file() and f.resolve().is_relative_to(dist.resolve()):
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app
