"""Settings and paths.

Values come from ``~/.env`` then ``./.env`` (the project file wins) via
``dotenv_values``. Nothing is exported into ``os.environ``, so the subprocesses
this project starts (transcript·lab) see only their own environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def _env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in (Path.home() / ".env", ROOT / ".env"):
        if path.exists():
            merged.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    merged.update({k: v for k, v in os.environ.items() if k.startswith(("RT_", "ROTATION_"))})
    if "MLFLOW_TRACKING_URI" in os.environ:
        merged["MLFLOW_TRACKING_URI"] = os.environ["MLFLOW_TRACKING_URI"]
    return merged


def supadata_keys(env: dict[str, str]) -> list[str]:
    """``SUPADATA_API_KEY`` then ``_2``, ``_3``…, stopping at the first gap (as transcript·lab)."""
    first = env.get("SUPADATA_API_KEY") or env.get("SUPERDATA_API_KEY")
    keys = [first] if first else []
    n = 2
    while env.get(f"SUPADATA_API_KEY_{n}"):
        keys.append(env[f"SUPADATA_API_KEY_{n}"])
        n += 1
    return keys


@dataclass(frozen=True)
class Settings:
    database_url: str
    ro_database_url: str
    admin_database_url: str
    mlflow_tracking_uri: str
    supadata_keys: tuple[str, ...]
    anthropic_api_key: str = ""
    channel: str = "@fxevolutionvideo"
    channel_id: str = "UCvJZEG5x-DVYZKTz--pS39w"
    channel_name: str = "FX Evolution - Trading Academy"
    # The first trading week in scope, keyed by its Friday (decision: 2023 onwards).
    first_week_friday: date = date(2023, 1, 6)
    cache_dir: Path = ROOT / ".rt"
    transcript_lab_root: Path = ROOT.parent / "transcript-rag-agent"
    transcript_lab_chroma: Path = ROOT.parent / "transcript-rag-agent" / ".yt-agent" / "chroma"
    experiment: str = "rotation-tracker/ingest"
    mining_experiment: str = "rotation-tracker/mining"


@lru_cache(maxsize=1)
def settings() -> Settings:
    e = _env()
    tra = Path(e.get("TRANSCRIPT_LAB_ROOT", str(ROOT.parent / "transcript-rag-agent")))
    return Settings(
        database_url=e.get("ROTATION_DATABASE_URL", ""),
        ro_database_url=e.get("ROTATION_RO_DATABASE_URL", ""),
        admin_database_url=e.get("ROTATION_ADMIN_DATABASE_URL", ""),
        mlflow_tracking_uri=e.get("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        supadata_keys=tuple(supadata_keys(e)),
        anthropic_api_key=e.get("ANTHROPIC_API_KEY", ""),
        first_week_friday=date.fromisoformat(e.get("RT_FIRST_WEEK_FRIDAY", "2023-01-06")),
        cache_dir=Path(e.get("RT_CACHE_DIR", str(ROOT / ".rt"))),
        transcript_lab_root=tra,
        transcript_lab_chroma=Path(
            e.get("TRANSCRIPT_LAB_CHROMA_PATH", str(tra / ".yt-agent" / "chroma"))
        ),
    )
