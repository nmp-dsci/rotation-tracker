"""The miner on synthetic inputs only: no transcript text, no live LLM call, no database."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rotation_tracker.mining import baseline, corpus, evaluate, universe
from rotation_tracker.mining.locate import Section, attach_marks, find, locate
from rotation_tracker.mining.resolve import Resolver, normalise, variants
from rotation_tracker.mining.schema import (
    AssetRef,
    Mention,
    Role,
    asset_stance,
    check,
    mention_stance,
)
from rotation_tracker.serving.app import create_app

ASSETS: list[tuple[str, str, str | None, str | None]] = [
    ("theme:semis", "theme", None, "SMH"),
    ("index:ndx", "index", None, "QQQ"),
    ("stock:TGT", "stock", "TGT", "TGT"),
    ("stock:NDAQ", "stock", "NDAQ", "NDAQ"),
    ("stock:NVDA", "stock", "NVDA", "NVDA"),
    ("stock:AI", "stock", "AI", "AI"),
    ("theme:ai", "theme", None, None),
    ("stock:BRK.B", "stock", "BRK.B", "BRK-B"),
    ("crypto:btc", "crypto", None, "BTC-USD"),
    # Same letters as an index or a futures symbol once the punctuation is stripped.
    ("stock:DJT", "stock", "DJT", "DJT"),
    ("stock:CLF", "stock", "CLF", "CLF"),
    ("stock:MOVE", "stock", "MOVE", "MOVE"),
    ("index:djt", "index", None, "^DJT"),
    ("commodity:oil", "commodity", None, "USO"),
    ("stock:sk-hynix", "stock", None, "000660.KS"),
    ("macro:fed", "macro", None, "^IRX"),
]
ALIASES = [
    ("semis", "theme:semis", False),
    ("chips", "theme:semis", False),
    ("nasdaq", "index:ndx", False),
    ("the cues", "index:ndx", False),
    ("target", "stock:TGT", True),
    ("nvidia", "stock:NVDA", False),
    ("ai", "theme:ai", False),
    ("berkshire", "stock:BRK.B", False),
    ("btc", "crypto:btc", False),
    ("bitcoin", "crypto:btc", False),
    ("cl", "commodity:oil", False),
]
R = Resolver(ALIASES, ASSETS, not_assets=["brett's"])


# ── resolve ───────────────────────────────────────────────────────────────────────────
def test_normalise_keeps_ampersand_and_drops_the() -> None:
    assert normalise("The S&P 500!") == "s&p 500"
    assert normalise("McDonald’s") == "mcdonalds"


def test_variants_strip_generic_words() -> None:
    assert variants("the semis sector")[-1] == "semis"
    assert "chips" in variants("some chips stocks")


@pytest.mark.parametrize(
    ("spoken", "ticker", "kind", "want"),
    [
        ("semis", None, "theme", ("theme:semis", "alias")),
        ("chip stocks", None, None, (None, "unknown")),  # an alias only if someone wrote it
        ("chips stocks", None, None, ("theme:semis", "alias")),
        ("Nasdaq", "QQQ", "index", ("index:ndx", "alias")),  # the index, not Nasdaq Inc.
        ("the cues", None, None, ("index:ndx", "alias")),  # auto-caption mishearing of the Qs
        ("Target", None, None, (None, "ambiguous")),  # "hit its price target"
        ("Target", "TGT", "stock", ("stock:TGT", "alias")),  # "Target, the retailer"
        ("C3.ai", "AI", "stock", ("stock:AI", "ticker")),  # a stock ticker beats the theme
        ("AI stocks", None, "theme", ("theme:ai", "alias")),
        ("Berkshire B", "BRK-B", "stock", ("stock:BRK.B", "ticker")),
        ("Berkshire B", "BRK.B", "stock", ("stock:BRK.B", "ticker")),  # a share class, not a venue
        ("DJT", "DJT", "stock", ("stock:DJT", "ticker")),  # Trump Media, by its own ticker
        # An index or futures symbol is never a US stock, whatever its letters spell.
        ("Dow Jones Transportation", "^DJT", "index", ("index:djt", "ticker")),  # by its proxy
        ("transports", "^DJT", "stock", ("index:djt", "ticker")),  # a wrong kind does not matter
        ("us oil", "CL=F", "commodity", ("commodity:oil", "alias")),  # its root, "cl"
        ("the move index", "^MOVE", "rates", (None, "unknown")),  # no curated row: not stock:MOVE
        ("bitcoin price", "BTC-USD", "crypto", ("crypto:btc", "alias")),
        ("Hynix", "000660.KS", "stock", ("stock:sk-hynix", "ticker")),  # not US-listed
        ("US 2-year", "^IRX", "rates", (None, "unknown")),  # a macro row's proxy is a stand-in
        ("BTC", "BTC", "crypto", ("crypto:btc", "alias")),
        ("Brett's", None, None, (None, "unknown")),  # breadth, misheard
        ("SpaceX", None, "stock", (None, "unknown")),
    ],
)
def test_resolve(spoken: str, ticker: str | None, kind: str | None, want: tuple[Any, str]) -> None:
    r = R.resolve(spoken, ticker, kind)
    assert (r.asset_id, r.how) == want


# ── locate ────────────────────────────────────────────────────────────────────────────
SEGS: list[dict[str, Any]] = [
    {"start_seconds": 0.0, "text": "welcome back to the synthetic show"},
    {"start_seconds": 4.0, "text": "money is moving out of widgets"},
    {"start_seconds": 9.5, "text": "and into gadgets this week"},
    {"start_seconds": 30.0, "text": "next chapter talks about levels"},
]


def sections() -> dict[int, Section]:
    s0 = Section(0, 0.0, 30.0, "Flows", "macro-flows", " ".join(x["text"] for x in SEGS[:3]))
    s1 = Section(1, 30.0, None, "Levels", "technicals", SEGS[3]["text"])
    attach_marks([s0, s1], SEGS)
    return {0: s0, 1: s1}


def test_locate_exact_gives_span_and_timestamp() -> None:
    secs = sections()
    hit = locate("Money is moving OUT of widgets, and into gadgets", 0, secs)
    assert hit is not None
    sec, f = hit
    assert f.how == "exact" and sec.text[f.start : f.end].startswith("money is moving")
    assert sec.t_at(f.start) == 4.0
    assert sec.t_at(sec.text.index("gadgets")) == 9.5


def test_locate_fuzzy_tolerates_a_misheard_word() -> None:
    f = find("money is moving out of widget and into gadgets this week", sections()[0].text)
    assert f is not None and f.how == "fuzzy" and f.score >= 0.9


def test_locate_drops_a_quote_that_is_not_there() -> None:
    assert locate("gold is breaking out to new highs today", 0, sections()) is None


def test_locate_falls_back_to_another_section() -> None:
    hit = locate("next chapter talks about levels", 0, sections())
    assert hit is not None and hit[0].idx == 1


# ── schema ────────────────────────────────────────────────────────────────────────────
def mk(play: str, direction: str, roles: list[Role]) -> Mention:
    return Mention(
        section=0,
        quote="q",
        play=play,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        assets=[
            AssetRef(spoken=f"a{i}", ticker=None, kind="theme", role=r) for i, r in enumerate(roles)
        ],
        speaker="him",
        reported_source=None,
        modality="observed",
        horizon="unspecified",
        confidence=0.5,
    )


def test_check_rejects_a_direction_that_does_not_fit_the_play() -> None:
    assert check(mk("valuation", "in", ["subject"])) == "bad-direction"
    assert check(mk("technical", "bullish", [])) == "no-asset"


def test_check_turns_rotation_subjects_into_sides() -> None:
    m = mk("rotation", "out", ["subject"])
    assert check(m) is None and m.assets[0].role == "from"


def test_unknown_play_fails_validation() -> None:
    with pytest.raises(ValueError):
        mk("vibes", "bullish", ["subject"])


def test_stance_rotation_in_is_bullish_and_out_is_bearish() -> None:
    assert asset_stance("rotation", "out_in", "from") == "bearish"
    assert asset_stance("rotation", "out_in", "to") == "bullish"
    assert asset_stance("relative", "a_over_b", "versus") == "bearish"
    assert asset_stance("valuation", "under", "versus") == "bearish"
    assert mention_stance("call", "avoid", ["subject"]) == "bearish"


# ── universe ──────────────────────────────────────────────────────────────────────────
NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|"
    "NextShares\n"
    """WDGT|Widget Technologies, Inc. - Class A Common Stock|Q|N|N|100|N|N
WDGTW|Widget Technologies, Inc. - Warrants|Q|N|N|100|N|N
SEMI|Synthetic Semis ETF|G|N|N|100|Y|N
ZZZT|Test Issue Corp - Common Stock|Q|Y|N|100|N|N
File Creation Time: 1028202600:00|||||||"""
)
OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
GDGT|Gadget Holdings Corporation Common Stock|N|GDGT|N|100|N|GDGT
UNTD|United Thing Group Incorporated Common Stock|N|UNTD|N|100|N|UNTD
GDGT$A|Gadget Holdings Corporation 5.0% Preferred Series A|N|GDGTpA|N|100|N|GDGT-A
BRK.B|Synthetic Hathaway Inc. New Common Stock|N|BRK.B|N|100|N|BRK.B
File Creation Time: 1028202600:00|||||||"""
SP500 = """<table><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th>
<th>Headquarters</th><th>Date added</th></tr>
<tr><td>WDGT</td><td>Widget Technologies</td><td>Information Technology</td><td>Semiconductors</td>
<td>X</td><td>2024-03-18</td></tr>
<tr><td>UNTD</td><td>United Thing</td><td>Industrials</td><td>Air Freight</td><td>Y</td>
<td>1999-01-01</td></tr></table>"""


def test_parse_listed_keeps_common_stock_and_funds_only() -> None:
    rows = universe.parse_listed(NASDAQ, OTHER)
    assert {r["ticker"] for r in rows} == {"WDGT", "SEMI", "GDGT", "UNTD", "BRK.B"}
    assert next(r for r in rows if r["ticker"] == "SEMI")["etf"]


def test_build_tags_membership_and_keeps_curated_aliases_first() -> None:
    cur = {"assets": [{"id": "theme:widgets", "kind": "theme", "name": "Widgets",
                       "proxy": "WDGT", "aliases": ["widget"]}]}  # fmt: skip
    ext = {"stocks": {"GDGT": ["gadget co"]}, "needs_cue": ["united thing"]}
    b = universe.build(
        cur,
        ext,
        universe.parse_listed(NASDAQ, OTHER),
        universe.parse_sp500(SP500),
        [],
        date(2026, 10, 28),
    )
    by = {a["id"]: a for a in b.assets}
    w = by["stock:WDGT"]
    assert (w["sp500"], w["sp500_added"], w["gics_sub_industry"]) == (
        True,
        date(2024, 3, 18),
        "Semiconductors",
    )
    assert by["fund:SEMI"]["kind"] == "fund" and by["stock:BRK.B"]["proxy"] == "BRK-B"
    assert b.aliases[("widget technologies", "stock:WDGT")] == (False, "listing-name")
    assert b.aliases[("widget", "theme:widgets")] == (False, "themes.yaml")
    assert ("widget", "stock:WDGT") not in b.aliases  # "Widget Technologies" → "widget" is taken
    assert b.aliases[("united thing", "stock:UNTD")] == (True, "listing-name")
    assert b.aliases[("gadget co", "stock:GDGT")] == (False, "extras.yaml")


# The real assets/*.yaml against one synthetic listing: names from the unknown queue.
REAL = universe.build(
    universe.curated(),
    universe.extras(),
    [
        {
            "ticker": "SPCX",
            "name": "Space Exploration Technologies Corp. Class A Common Stock",
            "exchange": "Nasdaq",
            "etf": False,
            "test": False,
        }
    ],
    [],
    [],
    date(2026, 10, 28),
)
REAL_R = Resolver(
    [(a, i, c) for (a, i), (c, _) in REAL.aliases.items()],
    [(a["id"], a["kind"], a["ticker"], a["proxy"]) for a in REAL.assets],
    universe.extras().get("not_assets") or [],
)


@pytest.mark.parametrize(
    ("spoken", "ticker", "kind", "want"),
    [
        ("SpaceX", None, "stock", "stock:SPCX"),  # listed since June 2026
        ("inor", None, "commodity", "commodity:iron-ore"),  # auto-caption "iron ore"
        ("aluminum", None, "commodity", "commodity:aluminium"),
        ("10 cent", "TCEHY", "stock", "stock:tencent"),  # not US-listed: a curated row
        ("Heinix", "000660.KS", "stock", "stock:sk-hynix"),
        ("New York Stock Exchange", "^NYA", "index", "index:nya"),
        ("5200", "^GSPC", "index", "index:spx"),  # a level, resolved by the ticker guess
        ("US 500 futures", "ES=F", "index", "index:spx"),
        ("UK oil", "BZ=F", "commodity", "commodity:oil"),
        ("us oil", "CL=F", "commodity", "commodity:oil"),
        ("Dow Jones Transportation average", "^DJT", "index", "index:djt"),
        ("dowr Transportation average", "^DJT", "index", "index:djt"),  # by the proxy alone
        ("Dow Jones Transportation average", "IYT", "index", "index:djt"),
        ("transports", "IYT", "theme", "index:djt"),  # Dow theory's transports
        ("transportation", "IYT", "sector", "theme:transports"),
        ("the move index", "^MOVE", "rates", "index:move"),
        ("the next move", None, "macro", None),  # "move" alone is a word, not the index
        ("Japanese 2-year yields", None, "rates", "rates:jgb"),
        ("terminal rate", None, "rates", "macro:fed"),
        ("Cardano", "ADA", "crypto", "crypto:ada"),
        ("trumpcoin", "TRUMP", "crypto", "crypto:trump"),
        ("other alts", None, "crypto", "crypto:alts"),
        # s03: the yield spreads, as he says them (rates:10y3m → fred:T10Y3M, rates:2s10s → T10Y2Y)
        ("10 versus 3 month spread of US Treasury yields", None, "rates", "rates:10y3m"),
        ("10 versus 3 month spread of US Treasury yields", "T10Y3M", "rates", "rates:10y3m"),
        ("us 2year versus us 10e", None, "rates", "rates:2s10s"),
        ("two year versus 10-year", None, "rates", "rates:2s10s"),
        ("the US 2-year versus 10 year", None, "rates", "rates:2s10s"),
        ("us 2 versus 10", None, "rates", "rates:2s10s"),
        ("2s10s", None, "rates", "rates:2s10s"),
        ("10 year", None, "rates", "rates:us10y"),  # the yield alone is still the 10-year
        ("metals", None, "commodity", None),  # too vague to pick one
        ("private equity funds", None, "credit", None),
    ],
)
def test_asset_files_resolve_the_unknown_queue(
    spoken: str, ticker: str | None, kind: str, want: str | None
) -> None:
    assert REAL_R.resolve(spoken, ticker, kind).asset_id == want


def test_clean_name_keeps_hyphenated_names_whole() -> None:
    assert universe.clean_name("Take-Two Interactive Software, Inc. Common Stock") == (
        "take two interactive software"
    )


# ── baseline ──────────────────────────────────────────────────────────────────────────
def test_baseline_finds_a_rotation_with_both_sides() -> None:
    text = "this week we saw money rotating out of widgets and into gadgets again"
    sec = Section(0, 0.0, None, None, "untagged", text)
    week = corpus.Week("AAAAAAAAAAA", date(2026, 10, 23), "t", None, {0: sec})
    scan = baseline.Scanner(
        [("widgets", "theme:widgets", "theme"), ("gadgets", "theme:gadgets", "theme")]
    )
    found = scan.scan(week)
    assert [(m.play, m.direction) for m in found] == [("rotation", "out_in")]
    assert [(a.spoken, a.role) for a in found[0].assets] == [("widgets", "from"), ("gadgets", "to")]
    assert found[0].quote in text


# ── eval ──────────────────────────────────────────────────────────────────────────────
def M(i: int, start: int, end: int, play: str, assets: tuple[str, ...] = ("a",)) -> evaluate.M:
    return evaluate.M(i, "v", 0, start, end, play, "in", frozenset(assets))


def test_score_matches_one_to_one_by_overlap_and_play() -> None:
    gold = [M(1, 0, 100, "rotation"), M(2, 200, 300, "flow"), M(3, 400, 500, "rotation")]
    pred = [
        M(10, 10, 90, "rotation"),
        M(11, 210, 290, "rotation"),
        M(12, 20, 80, "rotation", ("b",)),
    ]
    s = evaluate.score(pred, gold)
    rot = s["per_play"]["rotation"]
    assert (rot["tp"], rot["pred"], rot["gold"]) == (1, 3, 2)
    assert s["play_confusion"] == {"flow→rotation": 1}
    assert s["asset_accuracy"] == 1.0


def test_gate_reads_bars() -> None:
    g = evaluate.gate({"rotation_precision": 0.9, "rotation_recall": 0.7, "asset_accuracy": 0.95,
                       "unknown_rate": 0.02, "dropped_rate": None})  # fmt: skip
    assert [k for k, v in g.items() if not v["pass"]] == ["rotation_recall", "dropped_rate"]


# ── the viewer's miner routes ─────────────────────────────────────────────────────────
class FakeStore:
    def health(self) -> dict[str, Any]:
        return {"ok": True}

    def overview(self) -> dict[str, Any]:
        return {}

    def weeks(self) -> list[dict[str, Any]]:
        return []

    def week(self, video_id: str) -> dict[str, Any] | None:
        return None

    def chunks(self, video_id: str) -> list[dict[str, Any]]:
        return []

    def search(self, q: str, topics: list[str], order: str, limit: int) -> dict[str, Any]:
        return {}

    def chart(self, quarter: date | None, view: str = "themes") -> dict[str, Any]:
        return {}

    def pipeline(self) -> dict[str, Any]:
        return {}

    def mentions(self, **f: Any) -> dict[str, Any]:
        return {"filters": f}

    def assets(self, kind: str | None, q: str | None) -> dict[str, Any]:
        return {"kind": kind, "q": q}

    def asset(self, asset_id: str) -> dict[str, Any] | None:
        return {"id": asset_id} if asset_id == "stock:BRK.B" else None

    def mining(self) -> dict[str, Any]:
        return {"runs": []}

    def spot_checks(self) -> list[dict[str, Any]]:
        return []


class FakeWriter:
    def __init__(self) -> None:
        self.saved: list[tuple[Any, ...]] = []

    def save(
        self, mention_id: int, verdict: str, fixes: dict[str, Any], note: str | None
    ) -> dict[str, Any]:
        if mention_id == 404:
            raise LookupError("not in the queue")
        self.saved.append((mention_id, verdict, fixes, note))
        return {"id": 1, "verdict": verdict}


def client(label: bool, writer: FakeWriter | None = None) -> TestClient:
    from pathlib import Path

    return TestClient(
        create_app(FakeStore(), dist=Path("/nonexistent"), labeler=writer, label=label)
    )


def test_mentions_route_clamps_limit_and_passes_filters() -> None:
    r = client(False).get("/api/mentions?play=rotation&limit=9999&q=semis")
    f = r.json()["filters"]
    assert (f["play"], f["limit"], f["q"]) == ("rotation", 500, "semis")


def test_asset_route_accepts_dotted_ids_and_404s_unknown() -> None:
    c = client(False)
    assert c.get("/api/assets/stock:BRK.B").json() == {"id": "stock:BRK.B"}
    assert c.get("/api/assets/stock:NOPE").status_code == 404
    assert c.get("/api/assets/not an id").status_code == 422


def test_labels_are_read_only_without_the_flag() -> None:
    c = client(False)
    assert c.get("/api/labels").json() == {"label_mode": False, "items": []}
    assert c.post("/api/labels", json={"mention_id": 1, "verdict": "correct"}).status_code == 403
    assert c.get("/api/mining").json()["label_mode"] is False


def test_labels_write_with_the_flag() -> None:
    w = FakeWriter()
    c = client(True, w)
    r = c.post("/api/labels", json={"mention_id": 7, "verdict": "fix", "fixes": {"play": "flow"}})
    assert r.status_code == 200 and w.saved == [(7, "fix", {"play": "flow"}, None)]
    assert c.post("/api/labels", json={"mention_id": 404, "verdict": "wrong"}).status_code == 404
    assert c.post("/api/labels", json={"mention_id": 7, "verdict": "maybe"}).status_code == 422


class _FakeCon:
    def __init__(self, play: str) -> None:
        self.play = play
        self.inserted = False

    def __enter__(self) -> "_FakeCon":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> Any:
        class R:
            def __init__(s, row: Any) -> None:
                s.row = row

            def fetchone(s) -> Any:
                return s.row

        if "spot_checks" in sql:
            return R((self.play,))
        self.inserted = True
        return R((1, 7, "fix", {}, None, None))

    def commit(self) -> None:
        return None


def _labeler_with(monkeypatch: pytest.MonkeyPatch, play: str) -> tuple[Any, "_FakeCon"]:
    from rotation_tracker import db
    from rotation_tracker.serving.mining import Labeler

    con = _FakeCon(play)
    monkeypatch.setattr(db, "connect", lambda: con)
    return Labeler(), con


def test_direction_fix_alone_is_checked_against_the_stored_play(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rotation_tracker.mining.schema import DIRECTIONS

    lab, con = _labeler_with(monkeypatch, "rotation")
    bad = "no-such-direction"
    assert bad not in DIRECTIONS["rotation"]
    with pytest.raises(ValueError, match="does not fit play 'rotation'"):
        lab.save(7, "fix", {"direction": bad}, None)
    assert not con.inserted
    good = DIRECTIONS["rotation"][0]
    lab.save(7, "fix", {"direction": good}, None)
    assert con.inserted
