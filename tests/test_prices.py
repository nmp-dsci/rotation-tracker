"""s03: proxies/v2, the export handed to market-getdata, components, the fdw step, and the viewer's
prices with a fake market. Offline and synthetic: no Postgres, no market data."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from rotation_tracker.config import ROOT
from rotation_tracker.market import components, fdw, prices, proxies
from rotation_tracker.market.proxies import Line, Proxies, ProxyError
from rotation_tracker.mining.universe import curated
from rotation_tracker.serving import mining as serving_mining
from rotation_tracker.serving import store as store_mod
from rotation_tracker.serving import themes
from rotation_tracker.serving.app import create_app
from rotation_tracker.serving.store import Store

PX = proxies.load()
CURATED = curated()["assets"]


# ── proxies.yaml, the real file ───────────────────────────────────────────────────────
def test_every_curated_asset_has_a_row_and_every_row_is_curated() -> None:
    assert proxies.check_curated(PX, CURATED) == []
    assert PX.version == "proxies/v2"


def test_every_key_is_typed_one_primary_per_asset_and_none_has_a_reason() -> None:
    for aid, rows in PX.explicit.items():
        assert [r.role for r in rows].count("primary") == 1 and rows[0].role == "primary", aid
        for r in rows:
            assert r.series == proxies.NONE or proxies.SERIES.match(r.series), (aid, r.series)
            if r.series == proxies.NONE:
                assert r.role == "primary" and (r.note or "").strip() and len(rows) == 1, aid
            if proxies.source(r.series) == "basket":
                assert proxies.symbol(r.series) in PX.baskets, aid


# The plan's chart map: each Chart theme pinned to an asset, its primary and companions.
CHART_MAP = {
    "Semiconductors": ("theme:semis", "yahoo:SMH", ["yahoo:SOXX", "yahoo:NVDA"]),
    "Software & SaaS": ("theme:software", "yahoo:IGV", ["yahoo:XSW"]),
    "AI": ("theme:ai", "yahoo:AIQ", ["yahoo:SMH", "basket:mag7"]),
    "Big tech": ("theme:mag7", "basket:mag7", ["yahoo:MAGS", "yahoo:MGK"]),
    "Banks & financials": ("theme:banks", "yahoo:KBE", ["yahoo:XLF", "yahoo:KRE"]),
    "Energy & oil": ("sector:energy", "yahoo:XLE", ["yahoo:USO", "fred:DCOILWTICO"]),
    "Healthcare": ("sector:healthcare", "yahoo:XLV", ["yahoo:XBI"]),
    "Small caps": ("index:rut", "yahoo:IWM", ["yahoo:MDY"]),
    "Gold & silver": ("commodity:gold", "yahoo:GLD", ["yahoo:SLV", "yahoo:GDX"]),
    "Crypto": ("crypto:btc", "yahoo:BTC-USD", ["yahoo:ETH-USD", "basket:crypto"]),
    "Bonds & yields": (
        "rates:us10y", "fred:DGS10", ["yahoo:TLT", "yahoo:^TNX", "fred:DGS2", "fred:DGS30"]
    ),
    "The dollar": ("fx:dxy", "yahoo:DX-Y.NYB", ["fred:DTWEXBGS"]),
    "China": ("theme:china-stocks", "yahoo:FXI", ["yahoo:KWEB", "yahoo:CNY=X"]),
    "Utilities": ("sector:utilities", "yahoo:XLU", []),
    "Consumer": ("sector:discretionary", "yahoo:XLY", ["yahoo:XLP", "yahoo:XRT"]),
    "Industrials": ("sector:industrials", "yahoo:XLI", ["yahoo:IYT"]),
    "Real estate": ("sector:real-estate", "yahoo:XLRE", ["yahoo:ITB", "fred:MORTGAGE30US"]),
    "Defensives": (
        "theme:defensives", "basket:defensives", ["yahoo:XLP", "yahoo:XLU", "yahoo:XLV"]
    ),
}  # fmt: skip


def test_every_chart_theme_is_pinned_to_its_asset_and_series() -> None:
    assert set(themes.ASSET_OF) == {name for name, _ in themes.THEMES}
    for name, (aid, primary, companions) in CHART_MAP.items():
        assert themes.ASSET_OF[name] == aid
        rows = PX.resolve(aid, "theme", None)
        assert rows[0].series == primary, name
        assert [r.series for r in rows[1:]] == companions, name


# The 23 fills, as the owner accepted them (decision 4).
FILLS = {
    "theme:defensives": "basket:defensives", "macro:recession": "fred:T10Y3M",
    "crypto:market": "basket:crypto", "macro:inflation": "fred:T5YIE", "macro:china": "yahoo:FXI",
    "theme:ai": "yahoo:AIQ", "crypto:alts": "basket:alts", "macro:sentiment": "yahoo:^VIX",
    "macro:liquidity": "fred:WALCL", "macro:jobs": "fred:ICSA", "macro:tariffs": "none",
    "theme:hardware": "basket:hardware", "macro:housing": "yahoo:ITB", "macro:geopolitics": "none",
    "macro:consumer": "yahoo:XLY", "theme:cyclicals": "basket:cyclicals",
    "theme:data-centers": "yahoo:DTCR", "rates:jgb": "fred:IRLTLT01JPM156N",
    "macro:earnings": "none", "theme:meme-stocks": "basket:meme", "macro:debt": "none",
    "crypto:stablecoins": "none", "credit:private": "yahoo:BIZD",
    # the two yield-spread assets this branch adds
    "rates:10y3m": "fred:T10Y3M", "rates:2s10s": "fred:T10Y2Y",
}  # fmt: skip


def test_the_fills_are_as_accepted() -> None:
    assert len(FILLS) == 25
    for aid, series in FILLS.items():
        assert PX.resolve(aid, aid.split(":")[0], None)[0].series == series, aid


def test_a_listed_stock_or_fund_is_priced_by_its_own_ticker_in_yahoo_spelling() -> None:
    assert PX.resolve("stock:BRK.B", "stock", "BRK.B")[0].series == "yahoo:BRK-B"
    assert PX.resolve("fund:XME", "fund", "XME")[0].series == "yahoo:XME"
    assert PX.resolve("theme:nope", "theme", None) == ()
    assert PX.legacy("stock:BRK.B", "stock", "BRK.B") == "BRK-B"
    assert PX.legacy("rates:us10y", "rates", None) is None  # a FRED primary has no Yahoo symbol
    assert PX.legacy("index:vix", "index", None) == "^VIX"


def doc(assets: dict[str, Any], baskets: dict[str, str] | None = None) -> dict[str, Any]:
    return {"version": "proxies/v2", "baskets": baskets or {"pair": "A + B"}, "assets": assets}


@pytest.mark.parametrize(
    ("assets", "error"),
    [
        ({"theme:x": {"primary": "SMH"}}, "not a typed key"),
        ({"theme:x": {"primary": "yahoo:smh"}}, "not a typed key"),
        ({"theme:x": {"primary": "basket:nope"}}, "unknown basket"),
        ({"theme:x": {"primary": "none"}}, "needs a reason"),
        ({"theme:x": {"primary": "none", "reason": "r", "companions": ["yahoo:A"]}}, "companions"),
        ({"theme:x": {"primary": "yahoo:A", "companions": ["yahoo:A"]}}, "twice"),
        ({"theme:x": {"primary": "yahoo:A", "companions": ["none"]}}, "primary only"),
        ({"theme:x": {"primary": "yahoo:A", "reason": "r"}}, "use a note"),
        ({"theme:x": {"companions": ["yahoo:A"]}}, "needs a primary"),
        (
            {
                "theme:x": {
                    "primary": {
                        "series": "yahoo:A",
                        "from": date(2024, 1, 1),
                        "to": date(2023, 1, 1),
                    }
                }
            },
            "runs from",
        ),  # fmt: skip
        ({"theme:x": {"primary": {"series": "yahoo:A", "since": 2020}}}, "unknown field"),
    ],
)
def test_invalid_rows_are_refused(assets: dict[str, Any], error: str) -> None:
    with pytest.raises(ProxyError, match=error):
        Proxies.parse(doc(assets))


def test_a_wrong_version_is_refused() -> None:
    with pytest.raises(ProxyError, match="version"):
        Proxies.parse({"version": "proxies/v1", "assets": {}})


def test_check_needs_a_series_or_a_reasoned_none_for_every_mentioned_asset() -> None:
    px = Proxies.parse(doc({"macro:x": {"primary": "none", "reason": "context"},
                            "theme:y": {"primary": "basket:pair"}}))  # fmt: skip
    counts, problems = proxies.check(
        px, [("macro:x", "macro", None), ("theme:y", "theme", None), ("stock:Z", "stock", "Z")]
    )
    assert counts == {"assets": 3, "priced": 2, "none": 1, "unresolved": 0} and problems == []
    counts, problems = proxies.check(px, [("theme:lost", "theme", None)])
    assert counts["unresolved"] == 1 and problems == [
        "theme:lost (theme): no series and no reasoned none"
    ]


def test_rows_for_seed_give_one_primary_per_asset_and_list_the_unresolved() -> None:
    px = Proxies.parse(doc({"theme:y": {"primary": "basket:pair", "companions": ["fred:F1"]}}))
    rows, unresolved = proxies.rows_for(
        px, [("theme:y", "theme", None), ("stock:Z", "stock", "Z"), ("theme:lost", "theme", None)]
    )
    assert [(r.asset_id, r.series, r.role, r.ord) for r in rows] == [
        ("theme:y", "basket:pair", "primary", 0),
        ("theme:y", "fred:F1", "companion", 1),
        ("stock:Z", "yahoo:Z", "primary", 0),
    ]
    assert unresolved == ["theme:lost"]


# ── the export: the contract with market-getdata ──────────────────────────────────────
def synthetic_export() -> list[Line]:
    px = Proxies.parse(
        doc(
            {
                "theme:chips": {"primary": "yahoo:CHIP", "companions": ["yahoo:NVDA"]},
                "rates:y10": {"primary": "fred:DGS10", "companions": ["yahoo:BOND", "yahoo:^TNX"]},
                "theme:safe": {"primary": "basket:pair"},
                "macro:talk": {"primary": "none", "reason": "context"},
                "macro:vol": {"primary": "yahoo:^VIX"},
                "index:vix": {"primary": "yahoo:^VIX"},
            }
        )
    )
    cur = [("theme:chips", "theme"), ("rates:y10", "rates"), ("theme:safe", "theme"),
           ("macro:talk", "macro"), ("macro:vol", "macro"), ("index:vix", "index")]  # fmt: skip
    mentioned = [("theme:chips", "theme", None), ("stock:NVDA", "stock", "NVDA"),
                 ("stock:BRK.B", "stock", "BRK.B"), ("fund:CHIP", "fund", "CHIP")]  # fmt: skip
    listing = {"NVDA": "stock", "BRK-B": "stock", "CHIP": "fund", "BOND": "fund"}
    return proxies.export(px, cur, mentioned, listing)


def test_export_lines_follow_the_contract() -> None:
    got = {ln.series: (ln.kind, ln.reasons) for ln in synthetic_export()}
    assert got == {
        "yahoo:CHIP": ("fund", ("proxy", "named")),  # a listing: its own kind
        "yahoo:NVDA": ("stock", ("named", "companion")),
        "yahoo:BRK-B": ("stock", ("named",)),
        "yahoo:BOND": ("fund", ("companion",)),
        "yahoo:^TNX": ("rates", ("companion",)),  # no asset of its own: the one it accompanies
        "yahoo:^VIX": ("index", ("proxy",)),  # its own asset, not the macro stand-in
        "fred:DGS10": ("rates", ("proxy",)),
        "basket:pair": ("basket", ("proxy",)),
    }
    assert "none" not in got


def test_export_file_is_tab_separated_grouped_and_round_trips() -> None:
    lines = synthetic_export()
    text = proxies.render(lines)
    body = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert all(len(ln.split("\t")) == 3 for ln in body)
    assert [proxies.source(ln.split("\t")[0]) for ln in body] == ["yahoo"] * 6 + ["fred", "basket"]
    assert proxies.parse_export(text) == lines
    assert "yahoo:NVDA\tstock\tnamed,companion" in body
    assert text.endswith("\n") and "do not edit by hand" in text


def test_the_export_default_path_is_the_feed_repo() -> None:
    assert proxies.EXPORT_DEFAULT.parts[-3:] == ("market-getdata", "instruments",
                                                 "rotation-tracker.txt")  # fmt: skip


# ── components.yaml ───────────────────────────────────────────────────────────────────
def test_components_map_onto_curated_categories_and_every_gics_sector() -> None:
    c = components.load()
    ids = {a["id"] for a in CURATED}
    assert c.targets() <= ids
    assert len(c.sectors) == 11 and all(v.startswith("sector:") for v in c.sectors.values())
    sw = c.basis("theme:software")
    assert sw.sub_industries == ("Application Software", "Systems Software") and sw.defined
    assert c.basis("theme:regional-banks").sub_industries == ("Regional Banks",)
    assert c.basis("index:spx").index == "sp500"
    assert not c.basis("commodity:gold").defined


def test_components_parse_refuses_an_unknown_flag() -> None:
    with pytest.raises(ValueError, match="index flags"):
        components.Components.parse({"version": "components/v1", "indexes": {"index:x": "russell"}})


# ── the fdw step ──────────────────────────────────────────────────────────────────────
class Recorder:
    """Stands in for a superuser connection; nothing must reach it when the step skips."""

    def __init__(self) -> None:
        self.sql: list[Any] = []

    def execute(self, *a: Any, **k: Any) -> Any:
        self.sql.append(a)
        raise AssertionError("the fdw step should not have run SQL")

    def transaction(self, *a: Any, **k: Any) -> Any:
        raise AssertionError("the fdw step should not have opened a transaction")


def test_fdw_skips_cleanly_without_env() -> None:
    con, said = Recorder(), list[str]()
    got = fdw.import_market(con, {}, said.append)  # type: ignore[arg-type]
    assert got["status"] == "skipped" and got["tables"] == [] and con.sql == []
    assert said and "skipped" in said[0] and "MARKET_" in said[0]
    assert fdw.target({"UNRELATED": "x"}) is None


def test_fdw_target_fills_defaults_and_never_shows_the_password() -> None:
    t = fdw.target({"MARKET_FDW_HOST": "postgres"})
    assert t is not None
    assert (t.host, t.port, t.dbname, t.user, t.password) == (
        "postgres", "5432", "market", "market_ro", "market_ro"
    )  # fmt: skip
    t2 = fdw.target({"MARKET_RO_USER": "reader", "MARKET_RO_PASSWORD": "s3cret-value"})
    assert t2 is not None and t2.host == "localhost" and t2.loopback
    assert "s3cret" not in repr(t2) and "s3cret" not in str(t2)


def test_fdw_ddl_binds_values_and_relaxes_the_password_rule_only_on_loopback() -> None:
    def render(t: fdw.Target) -> str:
        return "\n".join(s.as_string(None) for s in fdw._ddl(t, "market", "market_staging"))

    local = render(fdw.Target("localhost", "5432", "market", "market_ro", "it's"))
    assert "password_required 'false'" in local and "password 'it''s'" in local
    assert (
        "fetch_size '10000'" in local and 'DROP SCHEMA IF EXISTS "market_staging" CASCADE' in local
    )
    remote = render(fdw.Target("postgres", "5432", "market", "market_ro", "pw"))
    assert "password_required" not in remote


def test_no_sql_file_holds_a_password_or_the_fdw() -> None:
    for f in sorted(Path(ROOT / "sql").glob("*.sql")):
        text = f.read_text().lower()
        assert "user mapping" not in text and "password '" not in text, f.name


# ── the viewer's prices ───────────────────────────────────────────────────────────────
Q = [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1)]


def test_label_mode_and_quarters() -> None:
    assert [prices.label(s) for s in ("yahoo:SMH", "fred:DGS10", "basket:mag7", "none")] == [
        "SMH", "DGS10", "mag7 basket", "none"
    ]  # fmt: skip
    assert [prices.mode(s) for s in ("yahoo:A", "basket:b", "fred:F", "none")] == [
        "performance", "performance", "level", "none"
    ]  # fmt: skip
    assert prices.quarter_of(date(2026, 9, 30)) == date(2026, 7, 1)


def test_a_performance_line_is_rebased_at_its_first_quarter_with_a_value() -> None:
    got = prices.line("yahoo:A", {Q[1]: 50.0, Q[2]: 60.0}, Q)
    assert (
        got is not None and got["points"] == [None, 100.0, 120.0] and got["mode"] == "performance"
    )


def test_a_level_keeps_its_units_and_an_unpriced_asset_has_no_points() -> None:
    lvl = prices.line("fred:F", {Q[0]: -0.5, Q[2]: 0.25}, Q)
    assert lvl is not None and lvl["points"] == [-0.5, None, 0.25]
    none = prices.line("none", None, Q, reason="context")
    assert none is not None and none["points"] == [] and none["reason"] == "context"
    empty = prices.line("yahoo:A", {}, Q)
    assert empty is not None and empty["points"] == [] and empty["label"] == "A"
    assert prices.line(None, None, Q) is None


class FakeMarket:
    """market_staging, faked: quarter-end closes and instruments for a few series."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.asked: list[tuple[list[str], date]] = []

    def status(self) -> tuple[bool, str | None]:
        return (True, None) if self.available else (False, prices.NOT_IMPORTED.format(schema="m"))

    def quarter_closes(self, series: Any, since: date) -> dict[str, dict[date, float]]:
        self.asked.append((list(series), since))
        data = {"yahoo:CHIP": {Q[0]: 10.0, Q[1]: 12.0, Q[2]: 15.0}, "fred:F": {Q[2]: 4.5}}
        return {s: data[s] for s in series if s in data}

    def instruments(self, series: Any) -> dict[str, dict[str, Any]]:
        info = {"yahoo:CHIP": {"name": "Chip ETF", "first_date": date(2000, 6, 5)}}
        return {s: info[s] for s in series if s in info}


class Fixed:
    def __init__(self, value: Any) -> None:
        self.value = value

    def get(self) -> tuple[Any, str | None]:
        return self.value, None


PROXY_ROWS = {
    "theme:chips": [
        {"asset_id": "theme:chips", "series": "yahoo:CHIP", "role": "primary", "ord": 0,
         "from_date": None, "to_date": None, "note": None},
        {"asset_id": "theme:chips", "series": "fred:F", "role": "companion", "ord": 1,
         "from_date": None, "to_date": None, "note": "a level"},
    ],
    "macro:talk": [
        {"asset_id": "macro:talk", "series": "none", "role": "primary", "ord": 0,
         "from_date": None, "to_date": None, "note": "context, not a price"},
    ],
}  # fmt: skip


def fake_store(monkeypatch: pytest.MonkeyPatch, market: FakeMarket) -> Store:
    @contextmanager
    def no_db() -> Iterator[None]:
        yield None

    st = Store(market=market)
    counts = {
        "weeks": dict.fromkeys(Q, 13),
        "mentions": {"theme:chips": {Q[2]: 13}, "macro:talk": {Q[1]: 13}},
        "hit": {},
        "bullish": {},
        "bearish": {},
        "names": {"theme:chips": ("Chips", "theme"), "macro:talk": ("Talk", "macro")},
    }
    st._assets = Fixed(counts)  # type: ignore[assignment]
    st._market = Fixed(market.status())  # type: ignore[assignment]
    monkeypatch.setattr(st, "_con", no_db)
    monkeypatch.setattr(
        prices, "proxy_rows", lambda con, ids: {a: PROXY_ROWS[a] for a in ids if a in PROXY_ROWS}
    )
    return st


def test_chart_rows_carry_price_points_on_the_chart_quarters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = FakeMarket()
    c = fake_store(monkeypatch, m).chart(Q[1], "assets")
    by = {e["id"]: e for e in c["entries"]}
    chips = by["theme:chips"]["price"]
    assert (chips["series"], chips["label"], chips["mode"]) == ("yahoo:CHIP", "CHIP", "performance")
    assert chips["points"] == [100.0, 120.0, 150.0] and chips["first_date"] == date(2000, 6, 5)
    assert by["macro:talk"]["price"]["mode"] == "none"
    assert by["macro:talk"]["price"]["reason"] == "context, not a price"
    assert c["prices_available"] is True and c["prices_notice"] is None
    assert m.asked == [(["yahoo:CHIP"], Q[0])]  # primaries only, from the first quarter


def test_chart_without_market_keeps_each_series_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = FakeMarket(available=False)
    c = fake_store(monkeypatch, m).chart(None, "assets")
    chips = next(e for e in c["entries"] if e["id"] == "theme:chips")["price"]
    assert chips["series"] == "yahoo:CHIP" and chips["points"] == []
    assert c["prices_available"] is False and "market-getdata" in c["prices_notice"]
    assert m.asked == []  # nothing is read from a market that is not there


def test_asset_page_is_priced_by_its_primary_with_first_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = fake_store(monkeypatch, FakeMarket())
    monkeypatch.setattr(serving_mining, "asset", lambda con, aid: {"asset": {"id": aid}})
    monkeypatch.setattr(
        components, "components", lambda con, aid: {"defined": False, "holdings": "h"}
    )
    out = st.asset("theme:chips")
    assert out is not None
    pb = out["priced_by"]
    assert pb["primary"]["series"] == "yahoo:CHIP" and pb["primary"]["first_date"] == date(
        2000, 6, 5
    )
    assert [c["series"] for c in pb["companions"]] == ["fred:F"]
    assert pb["companions"][0]["mode"] == "level" and pb["prices_available"] is True
    assert out["components"] == {"defined": False, "holdings": "h"}


def test_api_serves_prices_from_a_fake_market(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for available in (True, False):
        st = fake_store(monkeypatch, FakeMarket(available))
        c = TestClient(create_app(st, dist=tmp_path))
        body = c.get("/api/chart", params={"view": "assets", "quarter": "2026-04-01"}).json()
        chips = next(e for e in body["entries"] if e["id"] == "theme:chips")
        assert chips["asset_id"] == "theme:chips"
        assert chips["price"]["points"] == ([100.0, 120.0, 150.0] if available else [])
        assert body["prices_available"] is available


def test_a_failing_market_read_is_a_notice_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken(FakeMarket):
        def quarter_closes(self, series: Any, since: date) -> dict[str, dict[date, float]]:
            raise RuntimeError("remote went away")

    st = fake_store(monkeypatch, Broken())
    st._prices = {"assets": store_mod._Cached(600, partial(st._price_lines, "assets"))}
    c = st.chart(None, "assets")
    assert c["prices_available"] is False and "remote went away" in c["prices_notice"]
    assert all(e["price"] is None for e in c["entries"])


def test_market_staging_status_reports_a_missing_schema_without_raising() -> None:
    class Con:
        def execute(self, q: Any, args: Any = None) -> Any:
            class R:
                def fetchone(self) -> tuple[bool]:
                    return (False,)

            return R()

    @contextmanager
    def connect() -> Iterator[Con]:
        yield Con()

    ok, notice = prices.MarketStaging(connect).status()
    assert ok is False and notice is not None and "rt db migrate" in notice

    @contextmanager
    def down() -> Iterator[Con]:
        raise OSError("connection refused")
        yield Con()

    ok, notice = prices.MarketStaging(down).status()
    assert ok is False and notice is not None and notice.startswith("Prices unavailable")


def test_proxies_yaml_has_no_duplicate_keys() -> None:
    class Strict(yaml.SafeLoader):
        pass

    def no_dupes(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
        keys = [loader.construct_object(k) for k, _ in node.value]
        assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]
        return dict(loader.construct_pairs(node))

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dupes)
    yaml.load(proxies.PROXIES_FILE.read_text(), Loader=Strict)  # noqa: S506 - SafeLoader subclass
