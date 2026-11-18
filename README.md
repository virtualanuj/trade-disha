# TradeDisha

A personal trading assistant for NSE index options (NIFTY and BANK NIFTY). It watches the
market live through a broker data feed, forms a bullish/bearish view every minute from
price trend, open interest, and premium behaviour, and recommends a specific call or put to
buy, with every reason visible. Recommendations can be paper-traded with one click; real
orders are always placed by the trader in their broker's app. TradeDisha never places an
order.

## Status

Milestones 0 to 6 make up version 1.0.0; the enhancements after it are listed by milestone.
[docs/plan.md](docs/plan.md) has the detail and what comes next.

- **0–6 (1.0.0):**
  - Market data: a provider interface with synthetic and replay feeds, instrument
    resolution, tick recording, and the live Upstox feed (daily login, real instrument
    master, websocket adapter). Starting after the open backfills today's candles and the
    opening-OI baseline.
  - Screen: WebSocket push with latency stamps, a live option chain, and 1-minute candles
    with EMA/VWAP/supertrend.
  - Signals: nine indicators combined into a per-minute bias with a visible evidence
    breakdown. A signal says which ATM call or put to buy, with entry, target and stop
    (index points via delta on expiry day). There's a signal card, chart markers and a daily
    history.
  - Paper trades: one click to open; they close at target, stop, the 15:15 square-off or by
    hand. P&L is net of costs, and a Journal page shows the results.
  - Running it: a status banner explains why the screen isn't live, feed outages are logged,
    and a Data panel deletes old raw ticks.
- **E1:** resizable panels, a hideable option chain, DD/MM/YYYY dates, and an index details
  view (day and 52-week range, change, futures premium, India VIX).
- **E2 / E3:** every panel can be minimised, and moved up and down.
- **C1:** the config is edited in the app and kept as numbered, tagged versions you can
  revert to. Each signal records the version it fired under.
- **S1 / S2:** every signal is scored by what its option did next. An order-flow trigger
  runs in shadow beside the minute-close rule.
- **E4:** a BULLION tab with live MCX gold and silver: day range, liquidity, circuit limits,
  next month, the gold/silver ratio and a minute chart.
- **E5:** bullion follows MCX hours with its own status, and index feed liveness counts NSE
  ticks only. A closed market's quiet feed shows muted, not red, under an amber banner.
- **E6:** bullion signals (buy or sell the GOLD/SILVER future on a trend-only bias, worked
  out 20 s after each minute close) and long/short paper trades through the MCX session,
  with their own Journal rows.
- **E7:** a waiting signal shows its fired and live entry, target and stop, and a paper
  trade takes the live levels at its fill.
- **E8:** a net-volume histogram under the price chart: buyer- minus seller-initiated
  volume per minute, signed from the futures ticks (Upstox does not supply it).
- **E9:** one full-width Market view panel (the meter with its evidence and order flow),
  with the signal on its own row above it.
- **E10:** a Headlines panel under the option chain: Upstox news for the 30 heaviest NIFTY
  and BANK NIFTY stocks, newest first, grouped by day, with unseen ones marked and stock
  chips coloured by index. It collapses, hides (a top-bar toggle brings it back) and
  shows alone on the BULLION tab. Display only.
- **E11:** the Index panel lists sector indices with level and change: ten sectors on
  NIFTY, the bank sub-indices on BANK NIFTY. ATM moves into Details.
- **E12:** the bias weighs macro evidence with a small share: the dollar (rebuilt from NSE
  currency futures), USD/INR, crude and gold for the indices; the dollar for bullion.

## Documents

| File | What it is |
|---|---|
| [docs/intent.md](docs/intent.md) | Requirements: purpose, scope, behaviour, qualities. No technical detail. |
| [docs/plan.md](docs/plan.md) | Development plan: iterative milestones, each ending in a runnable demo. |
| [docs/spec.md](docs/spec.md) | Architecture and detailed design: components, data model, indicators, signal engine, API, frontend, performance budget, code standards. |
| [docs/signal.md](docs/signal.md) | How a signal is worked out, end to end, for the indices and for bullion, with worked examples. |
| [docs/enhancements.md](docs/enhancements.md) | Requests made after 1.0.0, with what was decided and where each was built. |
| [docs/dd.md](docs/dd.md) | Data dictionary: every domain and technical term used in these documents. |

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
make frontend              # Vite on http://localhost:5173 (proxies /api and /ws to the backend)
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
| `upstox` | Live market data. Needs `TRADEDISHA_UPSTOX_API_KEY` / `_SECRET` in `.env` and an Upstox app whose redirect URL is `http://127.0.0.1:8000/api/auth/callback`. Press **Login** in the top bar once a day (the token ends at 03:30 IST). Set `TRADEDISHA_DB_PATH=data/live.sqlite` so live recordings stay apart from synthetic ones; replay with the same path replays a live day against that day's real instruments. The BULLION tab (MCX gold and silver) comes from this feed; a replay shows it only with `TRADEDISHA_REPLAY_BULLION=true`, which also replays that day's recorded bullion ticks. MCX closes at 23:30, or 23:55 while the US is on standard time: set `TRADEDISHA_MCX_CLOSE=23:55` for those months. |

Trading holidays are read from `config/nse-holidays.txt`, and MCX's (which differ, and
include evening-only days) from `config/mcx-holidays.txt`. Signal hours are enforced for
replay and Upstox feeds; the synthetic feed ignores them so signals can be seen at any
hour. For the indices that is 09:15 to `signal.last_signal_time` (15:00), with paper
trades squared off at `paper.square_off_time` (15:15). For bullion it is
`bullion.first_signal_time` to `last_signal_time` (09:15–22:45) while MCX is open, squared
off at `bullion.square_off_time` (23:00). With hours enforced, a trade opens only while its
market is live and before its square-off. Set `TRADEDISHA_ENFORCE_SIGNAL_HOURS` to override
either way.

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
make check                 # ruff check, ruff format --check, mypy, pytest, tsc, eslint, prettier, vitest
```

A milestone is not done while `make check` is red. The pre-commit hook runs the lint,
format and type gates (ruff, ruff format, mypy, ESLint, Prettier, tsc) on each commit, but
not the tests, so run `make check` before calling something done.

## Layout

```
backend/    Python package `tradedisha`, tests
frontend/   React app
config/     NSE and MCX holiday lists; params.toml, the starting parameters for a new database
docs/       intent, plan, spec, signal, enhancements, data dictionary
scripts/    check.sh
```
