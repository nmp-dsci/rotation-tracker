from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from rotation_tracker.serving import themes
from rotation_tracker.serving.app import create_app
from rotation_tracker.serving.store import decisions, paragraphs

Q1, Q2, Q3 = date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1)
WEEKS = {Q1: 13, Q2: 13, Q3: 13}


def test_rank_orders_by_mentions_per_wrap_and_marks_moves() -> None:
    mentions = {
        "Semis": {Q2: 130, Q3: 26},
        "Gold": {Q2: 26, Q3: 130},
        "Oil": {Q3: 13},
        "China": {Q2: 13},
    }
    entries, dropped = themes.rank(mentions, {}, WEEKS, Q3, size=2)
    assert [(e.theme, e.rank, e.prev_rank, e.move) for e in entries] == [
        ("Gold", 1, 2, "up"),
        ("Semis", 2, 1, "down"),
    ]
    assert entries[0].rate == 10.0
    assert entries[0].history == [0.0, 2.0, 10.0]
    assert dropped == []


def test_rank_new_entry_and_dropped() -> None:
    mentions = {"A": {Q2: 20, Q3: 20}, "B": {Q2: 10}, "C": {Q2: 5, Q3: 15}}
    entries, dropped = themes.rank(mentions, {}, WEEKS, Q3, size=2)
    assert [(e.theme, e.move) for e in entries] == [("A", "same"), ("C", "new")]
    assert dropped == ["B"]


def test_rank_first_quarter_has_no_previous() -> None:
    entries, dropped = themes.rank({"A": {Q1: 13}}, {"A": {Q1: 9}}, WEEKS, Q1)
    assert (entries[0].move, entries[0].prev_rank, entries[0].weeks_hit) == ("new", None, 9)
    assert dropped == []


def test_theme_patterns_are_whole_word() -> None:
    assert themes.pattern("ai") == r"\m(?:ai)\M"
    assert len({name for name, _ in themes.THEMES}) == len(themes.THEMES)


def seg(t: float, text: str) -> dict[str, Any]:
    return {"start_seconds": t, "text": text}


def test_paragraphs_break_at_a_sentence_after_the_interval() -> None:
    segs = [seg(0, "one"), seg(20, "two."), seg(45, "three"), seg(50, "four."), seg(60, "five")]
    assert paragraphs(segs, 0, None, every=40) == [
        {"t": 0, "text": "one two. three four."},
        {"t": 60, "text": "five"},
    ]


def test_paragraphs_keep_to_the_section_and_force_long_runs() -> None:
    segs = [seg(5, "before"), seg(10, "a"), seg(60, "b"), seg(95, "c"), seg(120, "after")]
    assert paragraphs(segs, 10, 120, every=40) == [
        {"t": 10, "text": "a b c"},
    ]
    long_run = [seg(t, "x") for t in range(0, 100, 10)]
    out = paragraphs(long_run, 0, None, every=40)
    assert out[0]["t"] == 0 and len(out) == 2


def test_decisions_come_from_the_plan_of_record() -> None:
    rows = decisions()
    assert rows and rows[0]["question"] == "Source"
    assert all(set(r) == {"question", "decision"} for r in rows)


class FakeStore:
    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "code_sha": "abc1234",
            "postgres": "up",
            "chroma": "up",
            "mlflow": "down",
        }

    def overview(self) -> dict[str, Any]:
        return {"status": {"picks": 1}}

    def weeks(self) -> list[dict[str, Any]]:
        return [{"video_id": "AAAAAAAAAAA", "week_friday": date(2026, 10, 23)}]

    def week(self, video_id: str) -> dict[str, Any] | None:
        return {"video_id": video_id} if video_id == "AAAAAAAAAAA" else None

    def chunks(self, video_id: str) -> list[dict[str, Any]]:
        return []

    def search(self, q: str, topics: list[str], order: str, limit: int) -> dict[str, Any]:
        return {"q": q, "topics": topics, "order": order, "limit": limit}

    def chart(self, quarter: date | None) -> dict[str, Any]:
        return {"quarter": quarter}

    def pipeline(self) -> dict[str, Any]:
        return {}

    def mentions(self, **filters: Any) -> dict[str, Any]:
        return {}

    def assets(self, kind: str | None, q: str | None) -> dict[str, Any]:
        return {}

    def asset(self, asset_id: str) -> dict[str, Any] | None:
        return None

    def mining(self) -> dict[str, Any]:
        return {}

    def spot_checks(self) -> list[dict[str, Any]]:
        return []


def test_api_routes_validate_and_404(tmp_path: Any) -> None:
    c = TestClient(create_app(FakeStore(), dist=tmp_path))
    assert c.get("/healthz").json()["mlflow"] == "down"
    assert c.get("/api/weeks").json()[0]["week_friday"] == "2026-10-23"
    assert c.get("/api/weeks/AAAAAAAAAAA").status_code == 200
    assert c.get("/api/weeks/BBBBBBBBBBB").status_code == 404
    assert c.get("/api/weeks/not-an-id").status_code == 422
    s = c.get("/api/search", params={"q": "rotation", "limit": 999}).json()
    assert (s["topics"], s["limit"]) == (["macro-flows", "untagged"], 200)
    assert c.get("/api/chart", params={"quarter": "2026-07-01"}).json() == {"quarter": "2026-07-01"}


def test_built_frontend_is_served_with_a_spa_fallback(tmp_path: Any) -> None:
    (tmp_path / "static").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "static" / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(FakeStore(), dist=tmp_path))
    assert c.get("/weeks/AAAAAAAAAAA").text == "<div id=root></div>"
    assert c.get("/static/app.js").text == "console.log(1)"
    assert c.get("/assets/stock:BRK.B").text == "<div id=root></div>"  # a page, not a file
    assert c.get("/api/nothing").status_code == 404
