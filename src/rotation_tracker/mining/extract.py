"""Every Claude call in this repo. play/v1: one call per week with structured output
(``WeekMentions``); ``ask`` for the gold second read.

The system prompt (prompt.md) is identical for every week and cached; the user turn is the
week's sections behind § markers. Interactive calls stream (long outputs); the backfill goes
through the Message Batches API at half price. Cost is computed from each response's usage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
from anthropic import transform_schema
from pydantic import BaseModel

from rotation_tracker.config import settings
from rotation_tracker.mining import corpus
from rotation_tracker.mining.schema import WeekMentions

MODEL = "claude-opus-5-5"
PROMPT = Path(__file__).with_name("prompt.md")
# $ per million tokens; cache writes are the 5-minute TTL (1.25x input).
PRICES = {"claude-opus-5-5": {"in": 4.0, "out": 20.0, "cache_read": 0.20, "cache_write": 5.0}}
BATCH = 0.5
# Thinking counts against max_tokens: at `max` a week overran 64k on all twelve gold weeks
# (28 Oct 2026), so the deeper efforts get the room Opus 5.5 allows.
MAX_TOKENS = {"low": 16_000, "medium": 24_000, "high": 40_000, "xhigh": 96_000, "max": 128_000}
# Output (mentions plus thinking) per week, for the up-front estimate only; runs log the truth.
# Measured on 28 Oct 2026: `high` averaged 15k–19k a run (7k–23k a week) over 31 weeks, `xhigh`
# 31k over the twelve gold weeks; the rest are scaled guesses.
OUT_GUESS = {"low": 5_000, "medium": 10_000, "high": 17_000, "xhigh": 32_000, "max": 100_000}
CHARS_PER_TOKEN = 3.47  # measured on this corpus with count_tokens (s01)


@lru_cache(maxsize=1)
def prompt_text() -> str:
    return PROMPT.read_text()


@lru_cache(maxsize=1)
def output_schema() -> dict[str, Any]:
    return transform_schema(WeekMentions)


def prompt_sha() -> str:
    body = prompt_text() + json.dumps(output_schema(), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def params(week: corpus.Week, effort: str, model: str = MODEL) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS[effort],
        "system": [{"type": "text", "text": prompt_text(), "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": corpus.render(week)}],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": output_schema()},
        },
    }


def client() -> anthropic.Anthropic:
    key = settings().anthropic_api_key
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in ~/.env or ./.env.")
    return anthropic.Anthropic(api_key=key, max_retries=4)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @classmethod
    def of(cls, u: Any) -> Usage:
        return cls(
            int(getattr(u, "input_tokens", 0) or 0),
            int(getattr(u, "output_tokens", 0) or 0),
            int(getattr(u, "cache_read_input_tokens", 0) or 0),
            int(getattr(u, "cache_creation_input_tokens", 0) or 0),
        )

    def usd(self, model: str = MODEL, batch: bool = False) -> float:
        p = PRICES[model]
        dollars = (
            self.input_tokens * p["in"]
            + self.output_tokens * p["out"]
            + self.cache_read_tokens * p["cache_read"]
            + self.cache_write_tokens * p["cache_write"]
        ) / 1e6
        return dollars * (BATCH if batch else 1.0)


@dataclass
class Result:
    video_id: str
    mentions: WeekMentions | None
    usage: Usage
    stop_reason: str | None
    error: str | None = None


def text_of(msg: Any) -> str:
    """The text block (structured output puts the JSON there, after any thinking)."""
    return next((str(b.text) for b in msg.content if getattr(b, "type", "") == "text"), "")


def parse(video_id: str, msg: Any) -> Result:
    usage = Usage.of(msg.usage)
    stop = getattr(msg, "stop_reason", None)
    text = text_of(msg)
    if stop in ("max_tokens", "refusal") or not text:
        return Result(video_id, None, usage, stop, f"stop_reason {stop}, {len(text)} chars")
    try:
        return Result(video_id, WeekMentions.model_validate_json(text), usage, stop)
    except ValueError as e:
        return Result(video_id, None, usage, stop, f"invalid JSON: {str(e)[:200]}")


def call(cl: anthropic.Anthropic, week: corpus.Week, effort: str, model: str = MODEL) -> Result:
    try:
        with cl.messages.stream(**params(week, effort, model)) as s:
            msg = s.get_final_message()
    except anthropic.APIError as e:
        return Result(week.video_id, None, Usage(), None, f"{type(e).__name__}: {str(e)[:200]}")
    return parse(week.video_id, msg)


def ask(
    cl: anthropic.Anthropic,
    system: str,
    body: str,
    schema_of: type[BaseModel],
    effort: str = "high",
    model: str = MODEL,
) -> tuple[Any, Usage]:
    """One structured-output call outside the weekly extractor (the gold second read).
    Returns the validated object, or None when the output does not validate."""
    config: Any = {
        "effort": effort,
        "format": {"type": "json_schema", "schema": transform_schema(schema_of)},
    }
    with cl.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS[effort],
        system=system,
        messages=[{"role": "user", "content": body}],
        output_config=config,
    ) as st:
        msg = st.get_final_message()
    try:
        return schema_of.model_validate_json(text_of(msg)), Usage.of(msg.usage)
    except ValueError:
        return None, Usage.of(msg.usage)


def submit(cl: anthropic.Anthropic, weeks: list[corpus.Week], effort: str, model: str) -> str:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    reqs = [
        Request(
            custom_id=w.video_id,
            params=MessageCreateParamsNonStreaming(**params(w, effort, model)),  # type: ignore[typeddict-item]
        )
        for w in weeks
    ]
    return str(cl.messages.batches.create(requests=reqs).id)


def batch_status(cl: anthropic.Anthropic, batch_id: str) -> tuple[str, dict[str, int]]:
    b = cl.messages.batches.retrieve(batch_id)
    c = b.request_counts
    counts = {
        k: int(getattr(c, k, 0) or 0)
        for k in ("processing", "succeeded", "errored", "canceled", "expired")
    }
    return str(b.processing_status), counts


def batch_results(cl: anthropic.Anthropic, batch_id: str) -> list[Result]:
    out = []
    for r in cl.messages.batches.results(batch_id):
        if r.result.type == "succeeded":
            out.append(parse(r.custom_id, r.result.message))
        else:
            detail = getattr(getattr(r.result, "error", None), "type", r.result.type)
            out.append(Result(r.custom_id, None, Usage(), None, f"batch {r.result.type}: {detail}"))
    return out


def estimate(weeks: list[corpus.Week], effort: str, batch: bool, model: str = MODEL) -> float:
    """Upper-bound dollars before a run: no cache discount, the output guess per week."""
    p = PRICES[model]
    sys_tokens = len(prompt_text()) / CHARS_PER_TOKEN + 1_500  # prompt + schema
    tin = sum(w.n_chars / CHARS_PER_TOKEN + sys_tokens for w in weeks)
    tout = OUT_GUESS[effort] * len(weeks)
    return (tin * p["in"] + tout * p["out"]) / 1e6 * (BATCH if batch else 1.0)
