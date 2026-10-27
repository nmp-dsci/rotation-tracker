"""Credit-free channel metadata from YouTube via yt-dlp.

* ``listing`` — one flat call per tab (Videos, Streams, Shorts): every id, title,
  duration and views, with yt-dlp's ``approximate_date`` guess at the date.
* ``video_meta`` — one watch-page lookup per video: the exact publish timestamp,
  chapters and caption availability. YouTube bot-checks these after a few hundred
  calls from one IP, so every result is cached under ``.rt/ytdlp/`` and a
  bot-check stops the run (``BotCheck``) so a re-run resumes where it left off.

Pattern copied from value-invest-agent ``catalog/ytdlp.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rotation_tracker.config import settings

TABS = ("videos", "streams", "shorts")


class BotCheck(RuntimeError):
    """YouTube asked yt-dlp to sign in to prove it is not a bot."""


def _cache_dir() -> Path:
    d = settings().cache_dir / "ytdlp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def listing(tab: str, refresh: bool = False) -> list[dict[str, Any]]:
    """Every entry on one channel tab, newest first, with its position in the listing."""
    cache = _cache_dir() / f"_listing_{tab}.json"
    if cache.exists() and not refresh:
        entries: list[dict[str, Any]] = json.loads(cache.read_text())["entries"]
        return entries
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noprogress": True,
        "extract_flat": True,
        "extractor_args": {"youtubetab": {"approximate_date": ["1"]}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/{settings().channel}/{tab}", download=False
        )
    entries = [
        {
            "id": e.get("id"),
            "pos": i,
            "title": e.get("title") or "",
            "timestamp": e.get("timestamp"),
            "duration": e.get("duration"),
            "view_count": e.get("view_count"),
        }
        for i, e in enumerate((info or {}).get("entries") or [], start=1)
        if e and e.get("id")
    ]
    cache.write_text(
        json.dumps({"fetched_at": datetime.now(UTC).isoformat(), "tab": tab, "entries": entries})
    )
    return entries


def cached_meta(video_id: str) -> dict[str, Any] | None:
    p = _cache_dir() / f"{video_id}.json"
    if not p.exists():
        return None
    try:
        meta: dict[str, Any] = json.loads(p.read_text())
    except json.JSONDecodeError:
        return None
    return meta


def write_meta(meta: dict[str, Any]) -> None:
    (_cache_dir() / f"{meta['id']}.json").write_text(json.dumps(meta))


def video_meta(video_id: str, need_chapters: bool = False) -> dict[str, Any]:
    """The slim per-video record. A seeded (``partial``) record is enough for dates;
    ``need_chapters`` forces a full lookup when only a seed is cached."""
    hit = cached_meta(video_id)
    if hit and not (need_chapters and hit.get("partial")):
        return hit
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "confirm you" in msg and "bot" in msg:
            raise BotCheck(msg) from e
        raise
    slim = {
        "id": info.get("id"),
        "title": info.get("title"),
        "description": (info.get("description") or "")[:2000],
        "timestamp": info.get("timestamp"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "channel_id": info.get("channel_id"),
        "live_status": info.get("live_status"),
        "availability": info.get("availability"),
        "has_auto_captions": bool(info.get("automatic_captions")),
        "chapters": [
            {
                "start_time": c.get("start_time"),
                "end_time": c.get("end_time"),
                "title": c.get("title"),
            }
            for c in (info.get("chapters") or [])
        ],
        "partial": False,
    }
    write_meta(slim)
    return slim


def seed_from(path: Path) -> int:
    """Load the s00 analysis lookups (``.rt/seed/exact_sample.json``) as partial records:
    exact timestamps, no chapters. Never overwrites a full record."""
    rows = json.loads(path.read_text())
    n = 0
    for r in rows:
        if cached_meta(r["id"]):
            continue
        ts = int(datetime.fromisoformat(r["utc"]).timestamp())
        write_meta(
            {
                "id": r["id"],
                "title": r["title"],
                "timestamp": ts,
                "duration": r.get("dur"),
                "live_status": None if r.get("live") in (None, "NA") else r["live"],
                "chapters": None,
                "partial": True,
            }
        )
        n += 1
    return n
