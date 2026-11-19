# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TradeDisha is a single-user, localhost trading assistant for NSE index options (NIFTY,
BANK NIFTY). It takes a live broker feed, computes a bullish/bearish bias at each
1-minute close, raises buy-call / buy-put signals with the evidence shown, and tracks
paper trades. One Python process (FastAPI + asyncio + one SQLite file) and one React page.

**Hard rule: there is no real-order code path, and none is ever added, not even behind a
flag.** The Upstox code covers auth, market data, instruments and candles only.

## Commands

Python is managed with uv and lives in `backend/`; run every `uv` command from there.
The frontend uses npm in `frontend/`.

```bash
make setup      # uv sync, npm install, install the pre-commit hook
make backend    # API on http://127.0.0.1:8000, reload on change
make frontend   # Vite on http://localhost:5173, proxies /api and /ws to the backend
make start      # build the frontend and serve everything from :8000
make check      # every gate: ruff check, ruff format --check, mypy, pytest, then frontend check
```

Individual gates and single tests:

```bash
cd backend
uv run pytest tests/test_signals.py                 # one file
uv run pytest tests/test_signals.py::test_name      # one test
uv run pytest -k "reversal"                         # by keyword
uv run ruff check . && uv run ruff format --check . && uv run mypy

cd frontend
npx vitest run src/components/SignalCard/SignalCard.test.tsx   # one file
npx vitest run -t "name of the test"                           # by name
npm run typecheck && npm run lint && npm run format:check      # eslint runs with --max-warnings 0
```

A milestone is not done while `make check` is red. The pre-commit hook runs ruff (with
`--fix`), ruff format, mypy and the frontend lint gates, but not the tests.

## Running without the market

`TRADEDISHA_FEED_PROVIDER` in `.env` (repo root, all keys prefixed `TRADEDISHA_`, see
`backend/tradedisha/config.py`) selects the feed:

- `synthetic` (default): random-walk market, ticks around the clock, ignores market hours.
  Tests use this through the `settings` / `client` fixtures in `backend/tests/conftest.py`.
- `replay`: replays a recorded day from SQLite and drives the app clock from tick
  timestamps. `TRADEDISHA_REPLAY_SPEED=0` runs flat out; `TRADEDISHA_REPLAY_DROP` withholds
  time ranges for fault injection; `TRADEDISHA_REPLAY_BULLION=true` also replays the day's
  `bullion_ticks` (contracts from the cached MCX file, no network). Replay does not
  re-record ticks.
- `upstox`: live feed; needs API key/secret and a daily login through the app. MCX hours
  are `TRADEDISHA_MCX_OPEN` / `TRADEDISHA_MCX_CLOSE` (23:30, or 23:55 while the US is on
  standard time; changed by hand) and `config/mcx-holidays.txt`.

Live recordings are kept in a separate file (`TRADEDISHA_DB_PATH=data/live.sqlite`)
because synthetic and live data use the same instrument keys. `data/` is gitignored.

## Backend architecture (`backend/tradedisha/`)

`main.py:build_state` constructs every long-lived object once and hangs it on
`app.state.td` as an `AppState`; routers reach it through the `State` dependency in
`api/deps.py`. The centre of the runtime is `market/session.py:FeedSession`, which owns
the provider and wires the pipeline in `_start()`:

```
MarketDataProvider (feed/synthetic | replay | upstox)
  -> TickBus (feed/bus.py, sync fan-out of StampedTick)
       -> TickStore (batched SQLite writes; skipped in replay)
       -> CandleBuilder (spot and future keys only)
            -> on 1-minute close -> BiasEngine -> SignalEngine -> PaperTradeManager
       -> ChainManager / ChainState (option chain, re-centring, subscription changes)
       -> PaperTradeManager.on_tick (target / stop)
       -> BullionTracker (market/bullion.py; MCX gold/silver, own CandleBuilder)
            -> bullion_tick_store (bullion_ticks; skipped in replay)
            -> BullionDesk (engine/bullion_desk.py), on mcx_clock:
                 candle close queued -> eval_offset_seconds later
                 -> BullionBiasEngine -> BullionSignalEngine -> its own PaperTradeManager
  -> listener lists on FeedSession (candle, bias, signal, trade, bullion candle)
       -> api/ws.py:WsHub -> browser
```

Bullion is loaded with the `upstox` provider, or in replay with `replay_bullion`.
`market/macro.py:MacroTracker` (Milestone E12) is loaded the same way: NSE currency
futures (the dollar-index proxy, USD/INR) and MCX crude, read by the macro group of both
biases (`indicators/macro.py`). Every `MCX_FO|` / `NCD_FO|` key is a side market
(`FeedSession.is_side_market`): never the index candles or liveness, recorded in
`bullion_ticks`.
`market/gift.py:GiftNifty` (E14) is not on the socket: Upstox has GIFT Nifty only as
`GLOBAL_INDEX|SGX NIFTY`, refreshed every 120 s, so it is fetched over REST once NSE is
open, stored per day in `gift_nifty` (replay and `tools/score.py` read that row) and used
only as NIFTY's opening-gap vote in the macro group.

Headlines (spec §6.7) sit outside this pipeline: `market/news.py:NewsService` hangs on
`AppState.news`, polls Upstox's news API while the login is valid, and publishes
`NewsChanged` on the `EventBus`; `WsHub` sends a `news` frame. Display only, nothing stored,
and it never touches `FeedSession`. Upstox has news for `NSE_EQ` stocks only, so the stocks
come from `config/news-stocks.txt` (at most 30).

Things that are easy to get wrong:

- **Two fan-out mechanisms.** Hot-path data (ticks, candles, bias, signals, trades) goes
  through synchronous callback lists on `FeedSession`. `events.py:EventBus` is only for
  low-rate state changes (feed health, auth, strike-window change, parameters reloaded,
  headlines changed).
- **Time.** Nothing reads the wall clock directly. Use the injected `MarketClock`
  (`clock.py`) for market time, which in replay is a `DrivenClock` advanced by tick
  timestamps, so cut-offs and the 15:15 square-off behave as they did live.
  `epoch_ms_now()` is for wall-clock stamps (latency, log rows). Timestamps are epoch
  milliseconds; market times are IST.
- **Parameters vs settings.** `config.py:Settings` is process configuration and needs a
  restart. Everything that shapes the bias and signals is a `ParameterSet`
  (`parameters/model.py`), edited in the UI and stored as numbered, tagged versions in the
  `config_versions` table; the highest version is in force and `parameters/service.py`
  never rewrites one (a revert is a new version). `config/params.toml` only seeds version
  1 for a database that has none. Components take `params` as a callable so a save applies
  at the next minute close, and each signal stores the `config_version` it fired under. A
  new tunable goes in the model (with a `description`, which is the editor's help text) and
  the TOML, not in `Settings`.
- **Pure maths.** `indicators/` holds pure functions over candle and chain series. The
  engines in `engine/` orchestrate them and do the persistence. Each bias and signal is
  stored with its full evidence breakdown.
- **Schema.** `store/db.py` applies `store/migrations/NNN_*.sql` in order, tracked by
  `PRAGMA user_version`. Add a new numbered file; never edit one that has shipped.
  The connection is a single shared `sqlite3` connection in autocommit mode with WAL.
- **Starting can be deferred.** With `upstox` and no valid token the app comes up without
  a feed and `FeedSession.start()` is called from the login callback (`api/auth.py`); it
  is idempotent, and `_start()` does all network work before wiring anything. Parts of
  `FeedSession` (`chains`, `bias`, `signals`, `paper`, `provider`, `bullion`,
  `bullion_desk`) are `None` until then.
- **Degraded mode.** When the feed is silent during market hours, signals stop,
  paper-trade entry and manual close are refused, and fills after the gap are marked. See
  `feed_live()`, `_track_gap()` and spec §14. Liveness means NSE ticks arriving: bullion
  ticks share the socket but are judged separately against MCX hours (`mcx_clock`,
  `bullion_status()`), and only gate bullion signals and trades. Upstox stamps ticks with
  its send time, so a price frozen at the source (seen on 2026-11-16: index spot stuck from
  15:15 while futures traded) still counts as live. Check the `ticks` table for distinct
  `ltp` per minute before blaming the app.
- **Bullion has its own pipeline** (spec §6.6, §9a). GOLD and SILVER MCX futures come
  from the same Upstox socket but must never reach the shared `CandleBuilder` (it drives
  the index bias engine) or the `ticks` table (MCX trades until 23:30 and would stretch
  replays); they go to `BullionTracker`'s own builder and `bullion_ticks`.
  `engine/bullion_desk.py` runs bullion bias -> signals -> paper trades on `mcx_clock`,
  `eval_offset_seconds` after each minute close. Bullion signals are futures, long or short
  (`BUY_FUT` / `SELL_FUT`); paper P&L is side-aware and each `PaperTradeManager` owns only
  its market's trades (`PaperRules`). "overall" in the journal is index options only.
  Every bullion load step fails soft so the index feed always starts. Upstox's full quote
  returns the live price in `ohlc.close`, and an untraded future's daily candles carry
  placeholder prices (`parse_range(..., traded_only=True)`).
- **Generated code.** `feed/upstox_proto/` is protoc output and is excluded from ruff and
  mypy; do not edit it by hand.

## Frontend architecture (`frontend/src/`)

- `api/ws.ts:MarketSocket` keeps one WebSocket with exponential reconnect and feeds the
  Zustand store in `state/store.ts`. The `hello` frame replaces all live state; later
  frames (`tick`, `chain`, `candle`, `bias`, `signal`, `signal_live`, `paper_trade`,
  `stats`, `flow`, `bullion`, `bullion_candle`, `health`, `parameters`, `news`) update it.
  Live data is never polled.
- `selectedIndex` is an index or `BULLION_TAB` (`state/store.ts`), which is not in
  `instruments`; code keyed by the selected index must allow for it. The tab shows only
  while bullion data exists. The main-column panels show the **focus** (`App.tsx`): the
  selected index, or on BULLION the metal picked by `MetalSwitch`
  (`lib/useBullionMetal.ts`); bias, signals and gates are keyed by that name.
- A waiting signal carries `live` levels (entry, target, stop at the current price); the
  `signal_live` frame refreshes them once a second and never revives an ended signal.
- `api/client.ts` is plain `fetch` for history, the journal and mutations. Paper-trade
  actions wait for the server (no optimistic UI) because the fill price comes from it.
- `api/types.ts` is a hand-written mirror of `backend/tradedisha/api/schemas.py` and the
  WS frames. Change both sides together.
- Every frame carries `t_src`, `t_in`, `t_out`; `lib/latency.ts` adds receive and paint
  times and posts a per-minute summary. `?debug=1` shows the overlay. Budget: ingest to
  painted under 250 ms p95.
- Routing is the URL hash (`#journal`). Browser preferences (panel sizes, minimised
  panels, details open) go through `lib/usePref.ts` to `localStorage`.
- Dates are shown as DD/MM/YYYY; the API, config and file names stay ISO.
- Components live in `components/<Name>/<Name>.tsx` with the test beside them.

## Documents and how work is organised

- `docs/intent.md` requirements, `docs/spec.md` design (section numbers are cited in code
  comments), `docs/plan.md` milestones, `docs/signal.md` how a signal is worked out
  (indices and bullion), `docs/dd.md` data dictionary, `docs/enhancements.md` post-1.0
  requests.
- Work is done in milestones; each ends with a runnable demo, one commit
  (`Milestone N: ...`) and a README status update. A behaviour change is reflected in the
  spec and plan as well as the code.
- Trading logic (indicators, signal rules, paper-trade exits) is written test-first, with
  table-driven lifecycle tests and hypothesis property tests for score bounds.

The original plan named some tools that were not adopted (plan.md "Stack" lists them).
Trust `pyproject.toml` and `package.json`: there is no SQLAlchemy, numpy, orjson, import-linter, TanStack Query,
TanStack Virtual, Playwright test suite or OpenAPI type generation. The layering rule
still holds by convention: `api` depends on `engine` / `market`, which depend on `store`;
`indicators` imports nothing from `api`, `feed` or `store`.

## Code standards enforced by the gates

- Python 3.12, ruff with a broad rule set including `ANN` (annotate everything), `T20`
  (no `print`) and `PL` with at most 8 arguments, line length 100, mypy strict with the
  pydantic plugin over both `tradedisha` and `tests`.
- pytest runs with `asyncio_mode = "auto"`; async tests need no marker.
- TypeScript strict, typescript-eslint strict with zero warnings allowed, Prettier.
