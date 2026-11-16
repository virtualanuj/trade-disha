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
config edited and versioned in the app, and signals (buy ATM call or put with entry, target
and stop, expiry-day point targets via delta) with a signal card, chart markers and a
daily history; one-click paper trades tracked to target, stop, 15:15 square-off or manual
close, with net-of-cost P&L and a Journal page (hit rate, average win/loss, net result,
overall and per index). The live Upstox feed (daily login, real instrument master, websocket
adapter) is in place; starting after the open backfills today's candles and the opening-OI baseline. A status
banner says why the screen is not live (login, feed outage, market closed) and dims
last-known data; feed outages are logged; a Data panel deletes old raw ticks. After 1.0.0
(Milestone E1): resizable panels, a hideable option-chain panel, DD/MM/YYYY dates, and a details view on the index tile
(day and 52-week range, change on the day, futures premium, India VIX). Milestone E2: every panel can be
minimised to its title bar to make room for the others. Milestone E3: the panels of the main column can be moved
up and down, with market view and signal moving as a pair. Milestone C1: the config is edited in the app and kept as
numbered, tagged versions that can be reverted to, and every signal records its version. Milestone E4: a BULLION
tab with live gold and silver (MCX futures): day range, liquidity, circuit limits, next month, the gold/silver ratio
and a minute chart. See [docs/plan.md](docs/plan.md) for what comes next.

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

Every parameter that shapes the bias is edited in the app. The **Config** button in the top
bar shows the version in force and opens the editor: change values, type a tag, and save. A
valid save becomes the next numbered version and applies from the next minute close; an
invalid one is rejected with the failing fields and nothing changes. The **History** tab
lists every version and can revert to any of them (as a new version). Each signal shows the
config version it fired under; hover it for that version's values.

Versions are kept in the database, so the live and synthetic databases each have their own
history. `config/params.toml` only supplies version 1 for a new database.

Every signal is scored by what its option did next (target first, stop first or neither
within `outcome_horizon_minutes`), whether or not it was paper-traded; "Signals today"
shows it. To judge a parameter change before using it, replay recorded days with a trial
file and compare the scorecards:

```
cd backend
uv run python -m tradedisha.tools.score --db ../data/live.sqlite
uv run python -m tradedisha.tools.score --db ../data/live.sqlite --params /path/to/trial.toml
```

The recorded database is opened read-only; each day is replayed in a scratch copy.

Two entry rules exist (`signal.entry_mode`): `minute_close`, the original, and `trigger`,
which waits for live order flow to agree with a weaker bias and buys at the ask. The one
that is not live runs in shadow: its signals are listed greyed in "Signals today" and
scored on their own scorecard row, but cannot be traded. Switch only when the shadow row
has beaten the live one over several sessions.

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
