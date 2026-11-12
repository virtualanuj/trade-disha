# TradeDisha

A personal trading assistant for NSE index options (NIFTY and BANK NIFTY). It watches the
market live through a broker data feed, forms a bullish/bearish view every minute from
price trend, open interest, and premium behaviour, and recommends a specific call or put to
buy, with every reason visible. Recommendations can be paper-traded with one click; real
orders are always placed by the trader in their broker's app. TradeDisha never places an
order.

## Status

Milestones 0 to 2 complete on synthetic data: provider interface with synthetic and replay
feeds, instrument resolution, tick recording, WebSocket push with latency stamps, and a
dashboard with index tabs, live prices and a live option chain panel (PCR, max pain, OI
change heat, build-up classes, ATM highlight) that re-centres as the index moves. The
Upstox adapter and its OAuth login are deferred until broker credentials exist.
See [docs/plan.md](docs/plan.md) for what comes next.

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
- Data: Upstox API v2 (free with an Upstox account). Arrives in Milestone 1.

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make setup                 # uv sync, npm install, git pre-commit hook
cp .env.example .env       # fill in Upstox credentials from Milestone 1 onward
```

## Run

```bash
make backend               # FastAPI on http://127.0.0.1:8000 (reload on change)
make frontend              # Vite on http://localhost:5173 (proxies /api to the backend)
```

Open http://localhost:5173. Add `?debug=1` (or press **Latency**) for the per-hop latency
overlay.

### Feed modes

Set `TRADEDISHA_FEED_PROVIDER` in `.env`:

| Value | What it does |
|---|---|
| `synthetic` (default) | Random-walk prices for both indices, ticking regardless of market hours. Ticks are recorded to SQLite. `TRADEDISHA_SYNTHETIC_TREND_PER_TICK=0.02` adds an upward drift (in strike steps per spot tick) to exercise re-centring. |
| `replay` | Replays a recorded day from SQLite, driving the app clock from tick timestamps. `TRADEDISHA_REPLAY_DATE=YYYY-MM-DD` picks the day (default: latest); `TRADEDISHA_REPLAY_SPEED=0` runs as fast as possible. |
| `upstox` | Not implemented yet; needs an Upstox account. |

Trading holidays are read from `config/nse-holidays.txt`.

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
