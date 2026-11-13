# TradeDisha

A personal trading assistant for NSE index options (NIFTY and BANK NIFTY). It watches the
market live through a broker data feed, forms a bullish/bearish view every minute from
price trend, open interest, and premium behaviour, and recommends a specific call or put to
buy, with every reason visible. Recommendations can be paper-traded with one click; real
orders are always placed by the trader in their broker's app. TradeDisha never places an
order.

## Status

Milestones 0 to 6 complete: provider interface with synthetic and replay
feeds, instrument resolution, tick recording, WebSocket push with latency stamps, a live
option chain panel, 1-minute candles with EMA/VWAP/supertrend overlays, nine indicators
combined into a per-minute bias with a visible evidence breakdown, a tunable
`config/params.toml` with live reload, and signals (buy ATM call or put with entry, target
and stop, expiry-day point targets via delta) with a signal card, chart markers and a
daily history; one-click paper trades tracked to target, stop, 15:15 square-off or manual
close, with net-of-cost P&L and a Journal page (hit rate, average win/loss, net result,
overall and per index). The live Upstox feed (daily login, real instrument master, websocket
adapter) is in place; starting after the open backfills today's candles and the opening-OI baseline. A status
banner says why the screen is not live (login, feed outage, market closed) and dims
last-known data; feed outages are logged; a Data panel deletes old raw ticks. After 1.0.0
(Milestone E1): resizable panels, a hideable option-chain panel, DD/MM/YYYY dates, and a details view on the index tile
(day and 52-week range, change on the day, futures premium, India VIX). Milestone E2: every panel can be
minimised to its title bar to make room for the others. See [docs/plan.md](docs/plan.md) for what comes next.

## Documents

| File | What it is |
|---|---|
| [docs/intent.md](docs/intent.md) | Requirements: purpose, scope, behaviour, qualities. No technical detail. |
| [docs/plan.md](docs/plan.md) | Development plan: iterative milestones, each ending in a runnable demo. |
| [docs/spec.md](docs/spec.md) | Architecture and detailed design: components, data model, indicators, signal engine, API, frontend, performance budget, code standards. |
| [docs/dd.md](docs/dd.md) | Data dictionary: every domain and technical term used above. |

## Stack

- Backend: Python 3.12 (uv), FastAPI, asyncio, SQLite. Lint and types: ruff, mypy strict.
- Frontend: Vite, React 19, TypeScript strict, Tailwind v4. Lint: ESLint strict, Prettier,
  Vitest.
- Data: Upstox API (free with an Upstox account): OAuth login, V3 websocket market feed.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make setup                 # uv sync, npm install, git pre-commit hook
cp .env.example .env       # Upstox key and secret are needed only for the live feed
```

## Run

```bash
make backend               # FastAPI on http://127.0.0.1:8000 (reload on change)
make frontend              # Vite on http://localhost:5173 (proxies /api to the backend)
```

For daily use, one command builds the web app and serves everything from the backend:

```bash
make start                 # then open http://127.0.0.1:8000
```

In development, open http://localhost:5173. Add `?debug=1` (or press **Latency**) for the per-hop latency
overlay.

### Feed modes

Set `TRADEDISHA_FEED_PROVIDER` in `.env`:

| Value | What it does |
|---|---|
| `synthetic` (default) | Random-walk prices for both indices, ticking regardless of market hours. Ticks are recorded to SQLite. `TRADEDISHA_SYNTHETIC_TREND_PER_TICK=0.02` adds an upward drift (in strike steps per spot tick) to exercise re-centring. |
| `replay` | Replays a recorded day from SQLite, driving the app clock from tick timestamps. `TRADEDISHA_REPLAY_DATE=YYYY-MM-DD` picks the day (default: latest); `TRADEDISHA_REPLAY_SPEED=0` runs as fast as possible. `TRADEDISHA_REPLAY_DROP='["10:05:00-10:07:30"]'` withholds the ticks in those IST time ranges, to see how the app behaves through a feed outage. |
| `upstox` | Live market data. Needs `TRADEDISHA_UPSTOX_API_KEY` / `_SECRET` in `.env` and an Upstox app whose redirect URL is `http://127.0.0.1:8000/api/auth/callback`. Press **Login** in the top bar once a day (the token ends at 03:30 IST). Set `TRADEDISHA_DB_PATH=data/live.sqlite` so live recordings stay apart from synthetic ones; replay with the same path replays a live day against that day's real instruments. |

Trading holidays are read from `config/nse-holidays.txt`. Signal hours (09:15 to the
`last_signal_time` cut-off) are enforced for replay and Upstox feeds; the synthetic feed
ignores them so signals can be seen at any hour. The same switch governs paper trades:
with hours enforced, a trade opens only while the market is live and before
`square_off_time`, and open trades are squared off at that time. Set `TRADEDISHA_ENFORCE_SIGNAL_HOURS`
to override either way.

### Tuning the signal

Every parameter that shapes the bias lives in `config/params.toml`, commented. Edit it and
click **Reload config** in the top bar: a valid file applies from the next minute close; an
invalid one is rejected with the failing fields and the previous values stay in force. The
**Config** button opens a read-only view of the active values.

## Check

```bash
make check                 # ruff, mypy, pytest, tsc, eslint, prettier, vitest
```

A milestone is not done while `make check` is red. The pre-commit hook runs the same
gates on each commit.

## Layout

```
backend/    Python package `tradedisha`, tests
frontend/   React app
config/     NSE holiday list; tunable signal parameters from Milestone 3
docs/       intent, plan, spec, data dictionary
scripts/    check.sh
```
