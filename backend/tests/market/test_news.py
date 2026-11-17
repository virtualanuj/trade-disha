"""Headlines (spec §6.7): the stock list, merging Upstox's per-stock lists, the poller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from tradedisha.config import REPO_ROOT
from tradedisha.events import AuthChanged, EventBus, NewsChanged, ParametersChanged
from tradedisha.market.news import (
    MAX_NEWS_KEYS,
    Headline,
    NewsService,
    NewsStock,
    load_news_stocks,
    parse_news,
)
from tradedisha.parameters.model import News, ParameterSet
from tradedisha.parameters.schema import describe

# -- the stock list -----------------------------------------------------------------


def test_load_news_stocks_reads_symbol_and_key_and_skips_comments(tmp_path: Path) -> None:
    f = tmp_path / "news.txt"
    f.write_text("# top\nHDFCBANK NSE_EQ|INE040A01034\n\nSBIN  NSE_EQ|INE062A01020 # bank\n")
    assert load_news_stocks(f) == (
        NewsStock("HDFCBANK", "NSE_EQ|INE040A01034"),
        NewsStock("SBIN", "NSE_EQ|INE062A01020"),
    )


def test_load_news_stocks_reads_the_index_column(tmp_path: Path) -> None:
    f = tmp_path / "news.txt"
    f.write_text("ITC NSE_EQ|I N\nPNB NSE_EQ|P B\nSBIN NSE_EQ|S NB\n")
    assert [s.indices for s in load_news_stocks(f)] == [
        ("NIFTY",),
        ("BANKNIFTY",),
        ("NIFTY", "BANKNIFTY"),
    ]


def test_load_news_stocks_rejects_an_unknown_index_code(tmp_path: Path) -> None:
    f = tmp_path / "news.txt"
    f.write_text("ITC NSE_EQ|I N\nX NSE_EQ|X FIN\n")
    with pytest.raises(ValueError, match="line 2"):
        load_news_stocks(f)


def test_load_news_stocks_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_news_stocks(tmp_path / "absent.txt") == ()


def test_load_news_stocks_rejects_more_than_30(tmp_path: Path) -> None:
    f = tmp_path / "news.txt"
    f.write_text("".join(f"S{i} NSE_EQ|K{i}\n" for i in range(MAX_NEWS_KEYS + 1)))
    with pytest.raises(ValueError, match="30"):
        load_news_stocks(f)


@pytest.mark.parametrize("line", ["HDFCBANK", "HDFCBANK INE040A01034", "A NSE_EQ|X N extra"])
def test_load_news_stocks_rejects_bad_line(tmp_path: Path, line: str) -> None:
    f = tmp_path / "news.txt"
    f.write_text(f"SBIN NSE_EQ|INE062A01020\n{line}\n")
    with pytest.raises(ValueError, match="line 2"):
        load_news_stocks(f)


def test_load_news_stocks_rejects_a_repeated_key(tmp_path: Path) -> None:
    f = tmp_path / "news.txt"
    f.write_text("SBIN NSE_EQ|INE062A01020\nSBI NSE_EQ|INE062A01020\n")
    with pytest.raises(ValueError, match="line 2"):
        load_news_stocks(f)


def test_shipped_news_stocks_file_is_valid() -> None:
    stocks = load_news_stocks(REPO_ROOT / "config" / "news-stocks.txt")
    assert 1 <= len(stocks) <= MAX_NEWS_KEYS
    assert all(s.key.startswith("NSE_EQ|") for s in stocks)
    assert len({s.symbol for s in stocks}) == len(stocks)
    assert all(s.indices for s in stocks)  # every shipped stock says which index it moves
    assert {"HDFCBANK", "SBIN"} <= {s.symbol for s in stocks if "BANKNIFTY" in s.indices}


# -- parsing ------------------------------------------------------------------------


def _item(
    heading: str = "H", ts: object = 1_000, link: object = "https://x/1", summary: object = "S"
) -> dict[str, Any]:
    return {
        "heading": heading,
        "summary": summary,
        "thumbnail": "https://x/t.png",
        "article_link": link,
        "published_time": ts,
    }


SYMBOLS = {"NSE_EQ|A": "AAA", "NSE_EQ|B": "BBB"}


def test_parse_news_merges_the_same_article_across_stocks() -> None:
    data = {"NSE_EQ|A": [_item(link="https://x/1")], "NSE_EQ|B": [_item(link="https://x/1")]}
    assert parse_news(data, SYMBOLS) == [
        Headline(heading="H", summary="S", link="https://x/1", published_ts=1_000,
                 symbols=("AAA", "BBB")),
    ]  # fmt: skip


def test_parse_news_without_a_link_merges_by_heading() -> None:
    data = {
        "NSE_EQ|A": [_item(heading="Wrap", link=None)],
        "NSE_EQ|B": [_item(heading="Wrap", link=""), _item(heading="Other", link=None)],
    }
    out = parse_news(data, SYMBOLS)
    assert [(h.heading, h.symbols, h.link) for h in out] == [
        ("Wrap", ("AAA", "BBB"), None),
        ("Other", ("BBB",), None),
    ]


def test_parse_news_is_newest_first_and_stable_on_ties() -> None:
    data = {
        "NSE_EQ|A": [
            _item(heading="old", ts=1, link="l1"),
            _item(heading="tie-1", ts=5, link="l2"),
            _item(heading="new", ts=9, link="l3"),
        ],
        "NSE_EQ|B": [_item(heading="tie-2", ts=5, link="l4")],
    }
    assert [h.heading for h in parse_news(data, SYMBOLS)] == ["new", "tie-1", "tie-2", "old"]


@pytest.mark.parametrize(
    "item",
    [
        {"summary": "no heading", "published_time": 1},
        _item(heading="   "),
        _item(ts="yesterday"),
        _item(ts=None),
        _item(ts=True),
        "not an object",
    ],
)
def test_parse_news_skips_unusable_items(item: object) -> None:
    assert parse_news({"NSE_EQ|A": [item, _item(heading="good", link="g")]}, SYMBOLS) == [
        Headline("good", "S", "g", 1_000, ("AAA",))
    ]


def test_parse_news_missing_summary_is_none_and_unknown_key_is_its_own_symbol() -> None:
    out = parse_news({"NSE_EQ|Z": [_item(summary=None)], "NSE_EQ|A": "junk"}, SYMBOLS)
    assert out == [Headline("H", None, "https://x/1", 1_000, ("NSE_EQ|Z",))]


def test_parse_news_float_time_and_newest_time_of_a_merged_story() -> None:
    data = {"NSE_EQ|A": [_item(ts=1_000.0)], "NSE_EQ|B": [_item(ts=2_000)]}
    assert parse_news(data, SYMBOLS)[0].published_ts == 2_000


# -- the service --------------------------------------------------------------------


class FakeAuth:
    def __init__(self, token: str | None = "tok") -> None:
        self.token = token
        self.expired = 0

    async def mark_expired(self) -> None:
        self.expired += 1
        self.token = None


def _body(items: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    total = sum(len(v) for v in items.values())
    page = {"page_number": 1, "page_size": 100, "total_records": total, "total_pages": 1}
    return {"status": "success", "data": items, "metadata": {"page": page}}


Responder = Callable[[httpx.Request], httpx.Response]


class Upstox:
    """A mock transport whose reply can be changed between calls."""

    def __init__(self, reply: Responder) -> None:
        self.reply = reply
        self.calls = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self.reply(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


def _ok(items: dict[str, list[dict[str, Any]]]) -> Responder:
    return lambda _: httpx.Response(200, json=_body(items))


STOCKS = (NewsStock("AAA", "NSE_EQ|A"), NewsStock("BBB", "NSE_EQ|B"))


def _service(
    upstox: Upstox,
    auth: FakeAuth | None = None,
    *,
    poll: Callable[[], float] = lambda: 3600,
    stocks: tuple[NewsStock, ...] = STOCKS,
    config_error: str | None = None,
) -> tuple[NewsService, EventBus, list[NewsChanged]]:
    events = EventBus()
    seen: list[NewsChanged] = []
    events.subscribe(NewsChanged, seen.append)
    svc = NewsService(
        auth=auth or FakeAuth(),
        events=events,
        stocks=stocks,
        poll_seconds=poll,
        config_error=config_error,
        transport=upstox.transport,
    )
    return svc, events, seen


async def test_no_token_makes_no_request_and_reports_needs_login() -> None:
    upstox = Upstox(_ok({}))
    svc, _, seen = _service(upstox, FakeAuth(token=None))
    assert svc.status == "needs_login"
    await svc.refresh()
    assert upstox.calls == 0
    assert svc.status == "needs_login"
    assert seen == []


async def test_first_fetch_publishes_and_sets_ok() -> None:
    upstox = Upstox(_ok({"NSE_EQ|A": [_item(ts=1, link="a"), _item(heading="N", ts=2, link="b")]}))
    svc, _, seen = _service(upstox)
    assert str(svc.status) == "loading"
    await svc.refresh()
    assert svc.status == "ok"
    assert svc.error is None
    assert [h.heading for h in svc.items] == ["N", "H"]
    assert svc.fetched_at is not None
    assert len(seen) == 1


async def test_request_names_every_stock_with_the_token() -> None:
    sent: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=_body({}))

    svc, _, _ = _service(Upstox(reply))
    await svc.refresh()
    (req,) = sent
    assert req.headers["authorization"] == "Bearer tok"
    assert req.url.params["category"] == "instrument_keys"
    assert req.url.params["instrument_keys"] == "NSE_EQ|A,NSE_EQ|B"


async def test_same_items_again_publishes_nothing() -> None:
    upstox = Upstox(_ok({"NSE_EQ|A": [_item()]}))
    svc, _, seen = _service(upstox)
    await svc.refresh()
    await svc.refresh()
    assert upstox.calls == 2
    assert len(seen) == 1


async def test_500_keeps_last_items_and_reports_error_until_a_success() -> None:
    upstox = Upstox(_ok({"NSE_EQ|A": [_item()]}))
    svc, _, seen = _service(upstox)
    await svc.refresh()
    upstox.reply = lambda _: httpx.Response(500, json={})
    await svc.refresh()
    assert str(svc.status) == "error"
    assert "500" in (svc.error or "")
    assert [h.heading for h in svc.items] == ["H"]
    upstox.reply = _ok({"NSE_EQ|A": [_item()]})
    await svc.refresh()
    assert svc.status == "ok"
    assert svc.error is None
    assert len(seen) == 3


async def test_401_marks_token_expired_and_keeps_items() -> None:
    auth = FakeAuth()
    upstox = Upstox(_ok({"NSE_EQ|A": [_item()]}))
    svc, _, _ = _service(upstox, auth)
    await svc.refresh()
    upstox.reply = lambda _: httpx.Response(401, json={})
    await svc.refresh()
    assert auth.expired == 1
    assert svc.status == "needs_login"
    assert len(svc.items) == 1


async def test_transport_timeout_is_an_error_not_a_crash() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    svc, _, _ = _service(Upstox(boom))
    await svc.refresh()
    assert svc.status == "error"
    assert svc.error is not None


async def test_config_error_reports_error_and_makes_no_request() -> None:
    upstox = Upstox(_ok({}))
    svc, _, _ = _service(upstox, stocks=(), config_error="news-stocks.txt: line 3: bad")
    await svc.refresh()
    assert upstox.calls == 0
    assert svc.status == "error"
    assert svc.error == "news-stocks.txt: line 3: bad"


async def test_no_stocks_listed_is_ok_and_empty_without_a_request() -> None:
    upstox = Upstox(_ok({}))
    svc, _, _ = _service(upstox, stocks=())
    await svc.refresh()
    assert upstox.calls == 0
    assert svc.status == "ok"
    assert svc.items == []


async def test_a_login_wakes_the_poller() -> None:
    upstox = Upstox(_ok({}))
    svc, events, _ = _service(upstox)
    svc.start()
    try:
        for _ in range(100):
            if upstox.calls:
                break
            await asyncio.sleep(0.01)
        assert upstox.calls == 1
        await events.publish(AuthChanged("valid"))
        for _ in range(100):
            if upstox.calls == 2:
                break
            await asyncio.sleep(0.01)
        assert upstox.calls == 2
    finally:
        await svc.stop()


async def _calls_reach(upstox: Upstox, n: int, within_s: float = 1.0) -> bool:
    for _ in range(int(within_s / 0.01)):
        if upstox.calls >= n:
            return True
        await asyncio.sleep(0.01)
    return upstox.calls >= n


async def test_a_shorter_interval_saved_in_the_config_applies_at_once() -> None:
    interval = [3600.0]
    upstox = Upstox(_ok({}))
    svc, events, _ = _service(upstox, poll=lambda: interval[0])
    svc.start()
    try:
        assert await _calls_reach(upstox, 1)
        interval[0] = 0.05
        await events.publish(ParametersChanged(version=2, effective_from_minute_ts=0))
        assert await _calls_reach(upstox, 3)  # fetched again, then on the new interval
    finally:
        await svc.stop()


async def test_saving_the_config_does_not_fetch_early() -> None:
    upstox = Upstox(_ok({}))
    svc, events, _ = _service(upstox)
    svc.start()
    try:
        assert await _calls_reach(upstox, 1)
        await events.publish(ParametersChanged(version=2, effective_from_minute_ts=0))
        assert not await _calls_reach(upstox, 2, within_s=0.2)
    finally:
        await svc.stop()


# -- the interval is a config parameter (spec §3.2) ---------------------------------


def test_poll_seconds_is_in_the_config_with_limits_and_help() -> None:
    assert ParameterSet().news.poll_seconds == 180
    (spec,) = [s for s in describe(ParameterSet()) if s.path == "news.poll_seconds"]
    assert (spec.kind, spec.ge, spec.le) == ("integer", 30, 3600)
    assert "Upstox" in spec.help


@pytest.mark.parametrize("bad", [29, 3601, 0])
def test_poll_seconds_out_of_range_is_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="poll_seconds"):
        News(poll_seconds=bad)


def test_a_stored_version_without_news_still_loads() -> None:
    stored = ParameterSet().model_dump(mode="json")
    del stored["news"]
    assert ParameterSet.model_validate(stored).news == News()


def test_the_seed_file_sets_the_interval() -> None:
    from tradedisha.parameters.service import load_file  # noqa: PLC0415

    assert load_file(REPO_ROOT / "config" / "params.toml").news.poll_seconds == 180
