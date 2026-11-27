# TradeDisha

A personal trading assistant for NSE index options (NIFTY and BANK NIFTY) and MCX gold and
silver futures. It watches each market live through a broker data feed, forms a
bullish/bearish view every minute, and recommends a specific trade (a call or put to buy on
an index, a future to buy or sell on a metal) with every reason visible. Recommendations
can be paper-traded with one click, funded by a paper bank; real orders are always placed
by the trader in their broker's app. TradeDisha never places an order.

## What it does

The requirements are in [docs/intent.md](docs/intent.md), with enhancements not yet merged
into it in [docs/enhancements.md](docs/enhancements.md); how it was built, milestone by
milestone, is in [docs/plan.md](docs/plan.md).

- **Market data:** the live Upstox feed (daily login, Logout at any time), with synthetic
  and replay feeds for testing. Index spot and futures, the option chain around ATM, India
  VIX and the sector indices; SENSEX; MCX GOLD and SILVER near-month futures and their minis
  (GOLDM, SILVERM); the GOLDBEES and SILVERBEES ETFs on NSE; the currency futures and crude
  behind the macro evidence; GIFT Nifty for the opening gap; headlines for the
  heaviest index stocks. Ticks are recorded (bullion apart from the NSE day) and can be
  replayed; starting after the open backfills the day. NSE and MCX keep their own hours
  and holidays, and each is judged live on its own ticks.
- **Market view:** a per-minute bias for each index from price trend, open interest,
  premium behaviour and a small share of other markets (the dollar, USD/INR, crude, gold;
  GIFT Nifty's gap at the open for NIFTY). For each metal: trend, the future's
  open-interest build-up, order flow, and the dollar, USD/INR and the other metal. Every
  vote is visible, and any factor can be switched off for one index or metal.
- **Signals:** an index signal says which ATM call or put to buy, a bullion signal whether
  to buy or sell the future, with entry, target and stop (whole rupees; index points via
  delta on expiry day) shown as fired and live while it waits. Every index signal is
  scored by what its option did next; an order-flow trigger runs in shadow beside the
  minute-close rule. Bullion signals pause around hand-listed US data releases.
- **Paper trading:** one click to open from a signal, or by hand with no signal: any
  option from the chain or a metal's future or its mini, bought or sold, from a ticket
  with the signal rule's target and stop (or your own) and, for a future, its lots. Each
  metal's signal trades the full future or its mini, with default lots per contract, set
  in Config. Funded by a paper bank (an option blocks its premium, a future its margin,
  plus cost; ₹25 lakh to start, set in Config). Trades close at target, stop, the
  square-off or by hand, and the target and stop of an open trade can be changed; P&L is
  net of costs. Trades opened by hand are kept out of the signal stats. The Journal is the
  bank's statement: every deposit, withdrawal, trade block and settlement with the balance
  and money free after it. The Trades page lists open trades live and closed ones by day,
  each opening to its fills, signal, outcome and evidence, with the results under them.
- **Screen:** tabs by exchange: NSE (NIFTY, BANK NIFTY, BULLION with the gold and silver
  ETFs) and MCX (GOLD, SILVER); panels that resize, minimise and re-order; a top bar with
  the market and feed status, the pages, the tools and Login or Logout (hover Trades, Data
  or Latency for a quick look); under it a strip of rates (NIFTY, SENSEX, gold, silver and
  their ETFs, with the day's change; a click opens the tab); DD/MM/YYYY dates; dark and
  light themes. A banner says why the screen isn't live.
- **Config:** every tunable value is edited in the app (a drawer with Parameters, Factors
  and Versions), saved as a numbered, tagged version you can revert to; each signal
  records the version it fired under.
- **Data:** a Data panel deletes old raw ticks and gives the space back to the disk.

What is still open: the order-flow trigger goes live only once enough live sessions of
shadow scores show it is better; the bullion weights are starting values to be tuned on
recorded weeks; `chain.strike_window` and `chain.recenter_strikes` are shown in Config but
not read; SENSEX, the two ETFs and the minis are built and unit-tested but not yet seen on a
live day (spec §17).

## Documents

| File | What it is |
|---|---|
| [docs/intent.md](docs/intent.md) | Requirements: purpose, scope, behaviour, qualities. No technical detail. |
| [docs/plan.md](docs/plan.md) | Development plan and build history: the milestones, each ending in a runnable demo. |
| [docs/spec.md](docs/spec.md) | Architecture and detailed design: components, data model, indicators, signal engine, API, frontend, performance budget, code standards. |
| [docs/signal.md](docs/signal.md) | How a signal is worked out, end to end, for the indices and for bullion, with worked examples. |
| [docs/enhancements.md](docs/enhancements.md) | Enhancements, the companion to intent.md: each request as it was asked, what was decided and where it was built. Merged into intent.md by hand from time to time. |
| [docs/dd.md](docs/dd.md) | Data dictionary: every domain and technical term used in these documents. |
| [docs/strike_ladder_analysis.md](docs/strike_ladder_analysis.md) | Analysis (not built): what signals for ATM ±3 strikes would take. |

## Stack

- Backend: Python 3.12 (uv), FastAPI, asyncio, SQLite. Lint and types: ruff, mypy strict.
- Frontend: Vite, React 19, TypeScript strict, Tailwind v4. Lint: ESLint strict, Prettier,
  Vitest.
- Data: Upstox API (free with an Upstox account): OAuth login, V3 websocket market feed.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 20.19+, 22.13+ or 24+ (what Vite 8
and jsdom need).

```bash
make setup                 # uv sync, npm install, git pre-commit hook
cp .env.example .env       # Upstox key and secret are needed only for the live feed
```

## Run

```bash
make backend               # FastAPI on http://127.0.0.1:8000 (reload on change)
make frontend              # Vite on http://localhost:5173 (proxies /api and /ws to the backend)
make dev                   # both at once (backend in the background; Ctrl-C stops the frontend)
```

For daily use, one command builds the web app and serves everything from the backend:

```bash
make start                 # then open http://127.0.0.1:8000
```

Deleting old ticks (Data panel) gives the space back to the disk. A database file whose
incremental vacuum is off (an older one) needs this once, with the app stopped:

```bash
make compact               # the database in .env; needs free disk about the size of the data kept
```

In development, open http://localhost:5173. Add `?debug=1` (or press **Latency**) for the
per-hop latency overlay.

### Feed modes

Set `TRADEDISHA_FEED_PROVIDER` in `.env`:

| Value | What it does |
|---|---|
| `synthetic` (default) | Random-walk prices for both indices, ticking regardless of market hours. Ticks are recorded to SQLite. `TRADEDISHA_SYNTHETIC_TREND_PER_TICK=0.02` adds an upward drift (in strike steps per spot tick) to exercise re-centring. |
| `replay` | Replays a recorded day from SQLite, driving the app clock from tick timestamps. `TRADEDISHA_REPLAY_DATE=YYYY-MM-DD` picks the day (default: latest); `TRADEDISHA_REPLAY_SPEED=0` runs as fast as possible. `TRADEDISHA_REPLAY_DROP='["10:05:00-10:07:30"]'` withholds the ticks in those IST time ranges, to see how the app behaves through a feed outage. |
| `upstox` | Live market data. Needs `TRADEDISHA_UPSTOX_API_KEY` / `_SECRET` in `.env` and an Upstox app whose redirect URL is `http://127.0.0.1:8000/api/auth/callback`. Press **Login** in the top bar once a day (the token ends at 03:30 IST); **Logout** ends it sooner. Set `TRADEDISHA_DB_PATH=data/live.sqlite` so live recordings stay apart from synthetic ones; replay with the same path replays a live day against that day's real instruments. The MCX tabs (gold and silver, with their minis) come from this feed; a replay shows them only with `TRADEDISHA_REPLAY_BULLION=true`, which also replays that day's recorded bullion ticks. SENSEX and the NSE ETFs are recorded with the NSE ticks, so a replay of a day recorded with them shows them. The macro ticks (currency futures, crude) are recorded with the bullion ticks, so a replay has macro evidence only with that flag too; NIFTY's GIFT Nifty gap replays either way. MCX closes at 23:30, or 23:55 while the US is on standard time: set `TRADEDISHA_MCX_CLOSE=23:55` for those months. |

Trading holidays are read from `config/nse-holidays.txt`, and MCX's (which differ, and
include evening-only days) from `config/mcx-holidays.txt`. US data releases (CPI, payrolls)
that pause bullion signals are kept by hand in `config/us-events.txt`, in IST; restart
after editing it. Signal hours are enforced for
replay and Upstox feeds; the synthetic feed ignores them so signals can be seen at any
hour. For the indices that is 09:15 to `signal.last_signal_time` (15:00), with paper
trades squared off at `paper.square_off_time` (15:15). For bullion it is
`bullion.first_signal_time` to `last_signal_time` (09:15–22:45) while MCX is open, squared
off at `bullion.square_off_time` (23:00). With hours enforced, a trade opens only while its
market is live and before its square-off; one opened by hand, also before the signal
cut-off. Set `TRADEDISHA_ENFORCE_SIGNAL_HOURS` to override
either way.

### Tuning the signal

Every parameter that shapes the bias is edited in the app. The **Config** button in the top
bar shows the version in force and opens a drawer on the right with three tabs:

- **Parameters**: every value, with its explanation and allowed range on the line below its
  name. Change values, type a tag, and save. A valid save becomes the next numbered version
  and applies from the next minute close; an invalid one is rejected with the failing
  fields and nothing changes.
- **Factors**: a switch per factor of each index and metal, with a one-line explanation. A
  flip is saved at once as its own version.
- **Versions**: every version, the one in force marked; any other can be reverted to (as a
  new version).

Each signal shows the config version it fired under; hover it for that version's values.
Two parameters, `chain.strike_window` and `chain.recenter_strikes`, are not read yet: the
chain uses `TRADEDISHA_STRIKE_WINDOW` / `TRADEDISHA_RECENTER_STRIKES` (open item, spec §17).

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
uv run python -m tradedisha.tools.score --db ../data/live.sqlite --days 2026-11-17 2026-11-18
```

`--days` picks the days to replay (default: every recorded day).

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
config/     NSE and MCX holiday lists; us-events.txt, the US data releases that pause bullion;
            news-stocks.txt, the stocks whose headlines are shown; params.toml, the starting
            parameters for a new database
docs/       intent, plan, spec, signal, enhancements, data dictionary, strike ladder analysis
scripts/    check.sh
```
