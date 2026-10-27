"""MLflow runs on the central server (``MLFLOW_TRACKING_URI``).

Experiment ``rotation-tracker/ingest``; the id is never hardcoded.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import Any

from rotation_tracker.config import ROOT, settings


def _git_sha() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
            ).stdout.strip()
            or "unknown"
        )
    except OSError:
        return "unknown"


def log_run(name: str, kind: str, params: Mapping[str, Any], metrics: Mapping[str, float]) -> str:
    import mlflow

    s = settings()
    mlflow.set_tracking_uri(s.mlflow_tracking_uri)
    mlflow.set_experiment(s.experiment)
    tags = {
        "project": "rotation-tracker",
        "git_sha": _git_sha(),
        "env": "local",
        "billing": "supadata",
        "kind": kind,
    }
    with mlflow.start_run(run_name=name, tags=tags) as run:
        mlflow.log_params(dict(params))
        mlflow.log_metrics(dict(metrics))
        run_id: str = run.info.run_id
    return run_id
