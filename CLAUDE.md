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
  time ranges for fault injection. Replay does not re-record ticks.
- `upstox`: live feed; needs API key/secret and a daily login through the app.

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
  -> listener lists on FeedSession (candle, bias, signal, trade)
       -> api/ws.py:WsHub -> browser
```

Things that are easy to get wrong:

- **Two fan-out mechanisms.** Hot-path data (ticks, candles, bias, signals, trades) goes
  through synchronous callback lists on `FeedSession`. `events.py:EventBus` is only for
  low-rate state changes (feed health, auth, strike-window change, parameters reloaded).
- **Time.** Nothing reads the wall clock directly. Use the injected `MarketClock`
  (`clock.py`) for market time, which in replay is a `DrivenClock` advanced by tick
  timestamps, so cut-offs and the 15:15 square-off behave as they did live.
  `epoch_ms_now()` is for wall-clock stamps (latency, log rows). Timestamps are epoch
  milliseconds; market times are IST.
- **Parameters vs settings.** `config.py:Settings` is process configuration and needs a
  restart. Everything that shapes the bias and signals is in `config/params.toml`,
  validated by `parameters/model.py:ParameterSet` and reloadable from the UI. Components
  take `params` as a callable so a reload applies at the next minute close. A new tunable
  goes in the TOML and the model, not in `Settings`.
- **Pure maths.** `indicators/` holds pure functions over candle and chain series. The
  engines in `engine/` orchestrate them and do the persistence. Each bias and signal is
  stored with its full evidence breakdown.
- **Schema.** `store/db.py` applies `store/migrations/NNN_*.sql` in order, tracked by
  `PRAGMA user_version`. Add a new numbered file; never edit one that has shipped.
  The connection is a single shared `sqlite3` connection in autocommit mode with WAL.
- **Starting can be deferred.** With `upstox` and no valid token the app comes up without
  a feed and `FeedSession.start()` is called from the login callback (`api/auth.py`); it
  is idempotent, and `_start()` does all network work before wiring anything. Parts of
  `FeedSession` (`chains`, `bias`, `signals`, `paper`, `provider`) are `None` until then.
- **Degraded mode.** When the feed is silent during market hours, signals stop,
  paper-trade entry and manual close are refused, and fills after the gap are marked. See
  `feed_live()`, `_track_gap()` and spec §14.
- **Generated code.** `feed/upstox_proto/` is protoc output and is excluded from ruff and
  mypy; do not edit it by hand.

## Frontend architecture (`frontend/src/`)

- `api/ws.ts:MarketSocket` keeps one WebSocket with exponential reconnect and feeds the
  Zustand store in `state/store.ts`. The `hello` frame replaces all live state; later
  frames (`tick`, `chain`, `candle`, `bias`, `signal`, `paper_trade`, `stats`, `health`,
  `parameters`) update it. Live data is never polled.
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
  comments), `docs/plan.md` milestones, `docs/dd.md` data dictionary,
  `docs/enhancements.md` post-1.0 requests.
- Work is done in milestones; each ends with a runnable demo, one commit
  (`Milestone N: ...`) and a README status update. A behaviour change is reflected in the
  spec and plan as well as the code.
- Trading logic (indicators, signal rules, paper-trade exits) is written test-first, with
  table-driven lifecycle tests and hypothesis property tests for score bounds.

The spec and plan name some tools that were not adopted. Trust `pyproject.toml` and
`package.json`: there is no SQLAlchemy, numpy, orjson, import-linter, TanStack Query,
TanStack Virtual, Playwright test suite or OpenAPI type generation. The layering rule
still holds by convention: `api` depends on `engine` / `market`, which depend on `store`;
`indicators` imports nothing from `api`, `feed` or `store`.

## Code standards enforced by the gates

- Python 3.12, ruff with a broad rule set including `ANN` (annotate everything), `T20`
  (no `print`) and `PL` with at most 8 arguments, line length 100, mypy strict with the
  pydantic plugin over both `tradedisha` and `tests`.
- pytest runs with `asyncio_mode = "auto"`; async tests need no marker.
- TypeScript strict, typescript-eslint strict with zero warnings allowed, Prettier.
