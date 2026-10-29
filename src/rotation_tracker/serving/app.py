"""The viewer's API, and the built frontend from the same origin.

Read-only over what the pipeline has built: the weekly picks and their transcripts in Postgres,
transcript·lab's Chroma chunks, the ingest log, MLflow runs and the Supadata balance; and, from
s02, the mined mentions, the asset map, the miner's runs and eval. One write path exists: the
owner's spot-checks (POST /api/labels), and only when started with `rt serve --label`.

Run it: `uv run rt serve` (127.0.0.1:8089); in development also `cd frontend && npm run dev`
(127.0.0.1:5178, proxying /api and /healthz here).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rotation_tracker.config import ROOT
from rotation_tracker.serving.store import READ_TOPICS

DIST = ROOT / "frontend" / "dist"
VIDEO_ID = r"^[A-Za-z0-9_-]{11}$"
ASSET_ID = r"^[a-z]+:[A-Za-z0-9._^=-]{1,40}$"


class Reader(Protocol):
    def health(self) -> dict[str, Any]: ...
    def overview(self) -> dict[str, Any]: ...
    def weeks(self) -> list[dict[str, Any]]: ...
    def week(self, video_id: str) -> dict[str, Any] | None: ...
    def chunks(self, video_id: str) -> list[dict[str, Any]]: ...
    def search(self, q: str, topics: list[str], order: str, limit: int) -> dict[str, Any]: ...
    def chart(self, quarter: date | None, view: str = "themes") -> dict[str, Any]: ...
    def pipeline(self) -> dict[str, Any]: ...
    def mentions(self, **filters: Any) -> dict[str, Any]: ...
    def assets(self, kind: str | None, q: str | None) -> dict[str, Any]: ...
    def asset(self, asset_id: str) -> dict[str, Any] | None: ...
    def mining(self) -> dict[str, Any]: ...
    def spot_checks(self) -> list[dict[str, Any]]: ...


class Writer(Protocol):
    def save(
        self, mention_id: int, verdict: str, fixes: dict[str, Any], note: str | None
    ) -> dict[str, Any]: ...


class LabelIn(BaseModel):
    mention_id: int
    verdict: Literal["correct", "wrong", "fix"]
    fixes: dict[str, str] = {}
    note: str | None = None


def create_app(
    store: Reader | None = None,
    dist: Path = DIST,
    labeler: Writer | None = None,
    label: bool | None = None,
) -> FastAPI:
    if store is None:
        from rotation_tracker.serving.store import Store

        store = Store()
    st: Reader = store
    if label is None:
        label = os.environ.get("RT_LABEL") == "1"  # set by `rt serve --label`
    if label and labeler is None:
        from rotation_tracker.serving.mining import Labeler

        labeler = Labeler()
    writer = labeler if label else None
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
    def chart(
        quarter: date | None = None, view: Literal["themes", "assets"] = "themes"
    ) -> dict[str, Any]:
        return st.chart(quarter, view)

    @app.get("/api/pipeline")
    def pipeline() -> dict[str, Any]:
        return st.pipeline()

    # ---- s02: the miner ------------------------------------------------------------------
    @app.get("/api/mentions")
    def mentions(
        play: str | None = None,
        direction: str | None = None,
        stance: str | None = None,
        asset: str | None = None,
        kind: str | None = None,
        year: int | None = None,
        speaker: str | None = None,
        modality: str | None = None,
        week: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        return st.mentions(
            play=play,
            direction=direction,
            stance=stance,
            asset=asset,
            kind=kind,
            year=year,
            speaker=speaker,
            modality=modality,
            week=week,
            q=q[:200] if q else None,
            limit=max(1, min(limit, 500)),
            offset=max(0, offset),
        )

    @app.get("/api/assets")
    def assets(kind: str | None = None, q: str | None = None) -> dict[str, Any]:
        return st.assets(kind, q[:100] if q else None)

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str = PathParam(pattern=ASSET_ID)) -> dict[str, Any]:
        found = st.asset(asset_id)
        if found is None:
            raise HTTPException(404, f"{asset_id} is not in the asset map")
        return found

    @app.get("/api/mining")
    def mining() -> dict[str, Any]:
        return st.mining() | {"label_mode": writer is not None}

    @app.get("/api/labels")
    def labels() -> dict[str, Any]:
        return {"label_mode": writer is not None, "items": st.spot_checks()}

    @app.post("/api/labels")
    def save_label(body: LabelIn) -> dict[str, Any]:
        if writer is None:
            raise HTTPException(403, "read-only viewer: start it with `rt serve --label`")
        try:
            return writer.save(body.mention_id, body.verdict, body.fixes, body.note)
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    # ---- the built frontend ------------------------------------------------------------
    if (dist / "index.html").exists():
        # Vite's build.assetsDir is `static`: /assets/:id is a viewer page (s02).
        if (dist / "static").is_dir():
            app.mount("/static", StaticFiles(directory=dist / "static"), name="static")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404, f"no route /{path}")
            f = dist / path
            if path and f.is_file() and f.resolve().is_relative_to(dist.resolve()):
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app
