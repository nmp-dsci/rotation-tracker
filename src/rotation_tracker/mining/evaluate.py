"""``rt mine eval``: score an extractor run against the gold set.

Gold is the careful pass (gold/v1) on the twelve gold weeks, corrected by labels: the owner's
spot-checks win over the second read; a ``wrong`` verdict removes the mention, a ``fix`` replaces
its fields. A predicted mention matches a gold one when both sit in the same section, their
quote spans overlap by at least ``OVERLAP`` of the shorter, and the play agrees; pairs are
matched one-to-one, best overlap first.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from rotation_tracker import tracking
from rotation_tracker.config import settings
from rotation_tracker.mining.resolve import Resolver
from rotation_tracker.mining.schema import PLAYS

Log = Callable[[str], None]
OVERLAP = 0.3
GATE = {
    "rotation_precision": (">=", 0.85),
    "rotation_recall": (">=", 0.80),
    "asset_accuracy": (">=", 0.90),
    "unknown_rate": ("<", 0.10),
    "dropped_rate": ("<", 0.03),
}


@dataclass
class M:
    id: int
    video_id: str
    section: int
    start: int
    end: int
    play: str
    direction: str
    assets: frozenset[str] = field(default_factory=frozenset)


def overlap(a: M, b: M) -> float:
    if a.video_id != b.video_id or a.section != b.section:
        return 0.0
    inter = min(a.end, b.end) - max(a.start, b.start)
    return max(inter, 0) / max(min(a.end - a.start, b.end - b.start), 1)


def match(pred: list[M], gold: list[M], same_play: bool = True) -> list[tuple[M, M]]:
    cands = [
        (ov, p, g)
        for p in pred
        for g in gold
        if (not same_play or p.play == g.play) and (ov := overlap(p, g)) >= OVERLAP
    ]
    cands.sort(key=lambda c: -c[0])
    used_p: set[int] = set()
    used_g: set[int] = set()
    pairs = []
    for _, p, g in cands:
        if p.id in used_p or g.id in used_g:
            continue
        used_p.add(p.id)
        used_g.add(g.id)
        pairs.append((p, g))
    return pairs


def _ratio(a: float, b: float) -> float | None:
    return round(a / b, 4) if b else None


def score(pred: list[M], gold: list[M]) -> dict[str, Any]:
    pairs = match(pred, gold)
    out: dict[str, Any] = {"per_play": {}}
    for play in PLAYS:
        tp = sum(1 for p, _ in pairs if p.play == play)
        np_ = sum(1 for p in pred if p.play == play)
        ng = sum(1 for g in gold if g.play == play)
        prec, rec = _ratio(tp, np_), _ratio(tp, ng)
        f1 = round(2 * prec * rec / (prec + rec), 4) if prec and rec else None
        out["per_play"][play] = {"tp": tp, "pred": np_, "gold": ng, "precision": prec,
                                 "recall": rec, "f1": f1}  # fmt: skip
    tp = len(pairs)
    out["precision"], out["recall"] = _ratio(tp, len(pred)), _ratio(tp, len(gold))
    p, r = out["precision"] or 0, out["recall"] or 0
    out["f1"] = round(2 * p * r / (p + r), 4) if p and r else None
    out["matched"], out["pred"], out["gold"] = tp, len(pred), len(gold)
    out["direction_accuracy"] = _ratio(sum(p.direction == g.direction for p, g in pairs), tp)
    both = [(p, g) for p, g in pairs if p.assets and g.assets]
    out["asset_accuracy"] = _ratio(sum(p.assets == g.assets for p, g in both), len(both))
    out["asset_overlap"] = _ratio(sum(bool(p.assets & g.assets) for p, g in both), len(both))
    loose = match(pred, gold, same_play=False)
    out["play_confusion"] = dict(
        Counter(f"{g.play}→{p.play}" for p, g in loose if p.play != g.play)
    )
    out["span_matched_any_play"] = len(loose)
    out["rotation_precision"] = out["per_play"]["rotation"]["precision"]
    out["rotation_recall"] = out["per_play"]["rotation"]["recall"]
    return out


def load_run(con: psycopg.Connection, run_id: str, weeks: Iterable[str]) -> list[M]:
    rows = con.execute(
        """SELECT m.id, m.video_id, m.section_idx, m.span_start, m.span_end, m.play, m.direction,
                  coalesce(array_agg(a.asset_id) FILTER (WHERE a.asset_id IS NOT NULL), '{}')
           FROM rt.mentions m LEFT JOIN rt.mention_assets a ON a.mention_id = m.id
           WHERE m.run_id = %s AND m.video_id = ANY(%s)
           GROUP BY m.id""",
        (run_id, list(weeks)),
    ).fetchall()
    return [M(i, v, s, a, b, p, d, frozenset(ids)) for i, v, s, a, b, p, d, ids in rows]


def apply_labels(con: psycopg.Connection, gold: list[M], resolver: Resolver) -> list[M]:
    """Owner labels first, then the second read; ``wrong`` drops, ``fix`` replaces fields."""
    rows = con.execute(
        """SELECT DISTINCT ON (mention_id) mention_id, source, verdict, fixes
           FROM rt.labels WHERE mention_id = ANY(%s)
           ORDER BY mention_id, (source = 'owner') DESC, labeled_at DESC""",
        ([g.id for g in gold],),
    ).fetchall()
    labels = {mid: (src, verdict, fixes) for mid, src, verdict, fixes in rows}
    out = []
    for g in gold:
        lab = labels.get(g.id)
        if not lab:
            out.append(g)
            continue
        src, verdict, fixes = lab
        if verdict == "wrong":
            continue
        if verdict == "fix":
            if src == "owner":
                assets = g.assets
                if fixes.get("asset_id"):
                    assets = frozenset([fixes["asset_id"]])
                play = fixes.get("play") or g.play
                direction = fixes.get("direction") or g.direction
                g = M(g.id, g.video_id, g.section, g.start, g.end, play, direction, assets)
            else:
                keep = {
                    r.asset_id
                    for a in fixes.get("assets", [])
                    if a.get("right")
                    and (r := resolver.resolve(a["spoken"], None, a.get("kind"))).asset_id
                }
                extra = {
                    r.asset_id
                    for s in fixes.get("missing_assets", [])
                    if (r := resolver.resolve(s)).asset_id
                }
                g = M(g.id, g.video_id, g.section, g.start, g.end,
                      fixes.get("play") or g.play, fixes.get("direction") or g.direction,
                      frozenset(keep | extra) or g.assets)  # fmt: skip
        out.append(g)
    return out


def run_rates(con: psycopg.Connection, run_id: str, weeks: list[str]) -> dict[str, float | None]:
    k = con.execute(
        """SELECT coalesce(sum(mentions), 0), coalesce(sum(dropped), 0) FROM rt.mine_weeks
           WHERE run_id = %s AND video_id = ANY(%s)""",
        (run_id, weeks),
    ).fetchone()
    u = con.execute(
        """SELECT count(*), count(*) FILTER (WHERE a.asset_id IS NULL)
           FROM rt.mention_assets a JOIN rt.mentions m ON m.id = a.mention_id
           WHERE m.run_id = %s AND m.video_id = ANY(%s)""",
        (run_id, weeks),
    ).fetchone()
    kept, dropped = k if k else (0, 0)
    n, unknown = u if u else (0, 0)
    return {"dropped_rate": _ratio(dropped, kept + dropped), "unknown_rate": _ratio(unknown, n)}


def gate(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for k, (op, bar) in GATE.items():
        v = metrics.get(k)
        ok = v is not None and (v >= bar if op == ">=" else v < bar)
        out[k] = {"value": v, "bar": f"{op} {bar}", "pass": ok}
    return out


def evaluate(
    con: psycopg.Connection,
    run_id: str,
    gold_run_id: str,
    resolver: Resolver,
    baseline_run_id: str | None = None,
    agreement_run_id: str | None = None,
    log: Log = print,
) -> dict[str, Any]:
    weeks = [v for (v,) in con.execute("SELECT video_id FROM rt.gold_weeks")]
    gold = apply_labels(con, load_run(con, gold_run_id, weeks), resolver)
    pred = load_run(con, run_id, weeks)
    m = score(pred, gold) | run_rates(con, run_id, weeks)
    m["gate"] = gate(m)
    m["gate_pass"] = all(g["pass"] for g in m["gate"].values())
    m["weeks"] = len(weeks)
    labels = con.execute(
        """SELECT source, verdict, count(*) FROM rt.labels WHERE mention_id = ANY(%s)
           GROUP BY 1, 2""",
        ([g.id for g in load_run(con, gold_run_id, weeks)],),
    ).fetchall()
    m["labels"] = {f"{s}:{v}": n for s, v, n in labels}
    if baseline_run_id:
        b = score(load_run(con, baseline_run_id, weeks), gold)
        m["baseline"] = {k: b[k] for k in ("precision", "recall", "f1", "rotation_precision",
                                           "rotation_recall", "direction_accuracy",
                                           "asset_accuracy", "per_play")}  # fmt: skip
        m["baseline"]["run_id"] = baseline_run_id
    if agreement_run_id:
        other = con.execute(
            "SELECT array_agg(video_id) FROM rt.mine_weeks WHERE run_id = %s AND status = 'done'",
            (agreement_run_id,),
        ).fetchone()
        shared = [w for w in (other[0] if other else None) or [] if w in weeks]
        a = score(load_run(con, agreement_run_id, shared), load_run(con, run_id, shared))
        m["agreement"] = {"run_id": agreement_run_id, "weeks": len(shared), "f1": a["f1"],
                          "rotation_f1": a["per_play"]["rotation"]["f1"]}  # fmt: skip
    flat = {k: float(v) for k, v in m.items() if isinstance(v, (int, float)) and v is not None}
    for play, s in m["per_play"].items():
        for k in ("precision", "recall", "f1"):
            if s[k] is not None:
                flat[f"{play}_{k}"] = float(s[k])
    if "baseline" in m:
        for k in ("precision", "recall", "f1", "rotation_precision", "rotation_recall"):
            if m["baseline"][k] is not None:
                flat[f"v0_{k}"] = float(m["baseline"][k])
    if "agreement" in m and m["agreement"]["f1"] is not None:
        flat["run_to_run_f1"] = float(m["agreement"]["f1"])
    mid = None
    try:
        mid = tracking.log_run(
            f"eval-{run_id}",
            "mine-eval",
            {
                "run_id": run_id,
                "gold_run_id": gold_run_id,
                "baseline_run_id": baseline_run_id,
                "agreement_run_id": agreement_run_id,
                "gate_pass": m["gate_pass"],
            },  # fmt: skip
            flat,
            experiment=settings().mining_experiment,
            billing="none",
        )
    except Exception as e:
        log(f"  MLflow logging failed: {type(e).__name__}: {str(e)[:160]}")
    con.execute(
        """INSERT INTO rt.evals (run_id, gold_run_id, metrics, gate_pass, mlflow_run_id)
           VALUES (%s, %s, %s, %s, %s)""",
        (run_id, gold_run_id, Jsonb(m), m["gate_pass"], mid),
    )
    con.commit()
    m["mlflow_run_id"] = mid
    return m
