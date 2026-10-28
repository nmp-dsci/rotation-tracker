"""Supadata credit balance. ``GET /v1/me`` is free; transcripts are fetched by transcript·lab."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from rotation_tracker.config import settings

ME_URL = "https://api.supadata.ai/v1/me"


@dataclass(frozen=True)
class KeyBalance:
    n: int
    plan: str
    max_credits: int
    used_credits: int

    @property
    def left(self) -> int:
        return self.max_credits - self.used_credits


def balances() -> list[KeyBalance]:
    out = []
    for i, key in enumerate(settings().supadata_keys, start=1):
        req = urllib.request.Request(ME_URL, headers={"x-api-key": key})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        out.append(KeyBalance(i, str(d.get("plan")), int(d["maxCredits"]), int(d["usedCredits"])))
    return out


def credits_left() -> int:
    return sum(b.left for b in balances())
