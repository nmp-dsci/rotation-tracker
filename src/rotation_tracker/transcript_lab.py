"""transcript·lab: fetch through it, read back from it, never write to its store.

``index`` runs its own CLI in its own checkout (``index-rag <url> --metadata-json``),
so the transcript lands in *its* Chroma store exactly as if its workbench had
ingested it, for one Supadata credit: the metadata we pass replaces the second
call it would otherwise make. ``Corpus`` reads that store and writes nothing.

Patterns copied from value-invest-agent ``ingest/run.py`` and ``ingest/corpus.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from typing import Any

from rotation_tracker.config import settings


def supadata_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """The cached yt-dlp record in Supadata ``/metadata`` shape, which ``--metadata-json`` takes."""
    s = settings()
    created = None
    if meta.get("timestamp"):
        created = datetime.fromtimestamp(int(meta["timestamp"]), tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
    vid = meta["id"]
    return {
        "platform": "youtube",
        "type": "video",
        "id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": meta.get("title"),
        "description": meta.get("description"),
        "author": {"displayName": s.channel_name},
        "stats": {"views": meta.get("view_count")},
        "media": {"type": "video", "duration": meta.get("duration")},
        "createdAt": created,
        "additionalData": {"channelId": meta.get("channel_id") or s.channel_id},
    }


def index(meta: dict[str, Any], timeout_s: int = 900) -> tuple[int, str]:
    """Run ``index-rag`` for one video. Returns (returncode, last lines of output)."""
    s = settings()
    path = s.cache_dir / "ingest_meta" / f"{meta['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(supadata_metadata(meta)))
    argv = [
        "uv",
        "run",
        "python",
        "-m",
        "src.cli",
        "index-rag",
        f"https://www.youtube.com/watch?v={meta['id']}",
        "--metadata-json",
        str(path),
    ]
    # Summaries from the YouTube description, never an LLM: no cost beyond Supadata.
    env = {**os.environ, "YT_AGENT_SUMMARY_SOURCE": "description"}
    try:
        proc = subprocess.run(
            argv,
            cwd=s.transcript_lab_root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {timeout_s}s"
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    return proc.returncode, " | ".join(tail)[:500]


class Corpus:
    """Read-only view of transcript·lab's Chroma store (``raw_transcript:<video_id>``)."""

    def __init__(self) -> None:
        import chromadb

        self.client = chromadb.PersistentClient(path=str(settings().transcript_lab_chroma))
        self.raw_col = self.client.get_collection("raw_transcripts")

    def has(self, video_id: str) -> bool:
        return bool(self.raw_col.get(ids=[f"raw_transcript:{video_id}"]).get("ids"))

    def raw(self, video_id: str) -> dict[str, Any] | None:
        res = self.raw_col.get(ids=[f"raw_transcript:{video_id}"], include=["documents"])
        if not res.get("ids"):
            return None
        body: dict[str, Any] = json.loads((res.get("documents") or ["{}"])[0])
        return body
