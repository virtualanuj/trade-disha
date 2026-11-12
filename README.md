# TradeDisha

A personal trading assistant for NSE index options (NIFTY and BANK NIFTY). It watches the
market live through a broker data feed, forms a bullish/bearish view every minute from
price trend, open interest, and premium behaviour, and recommends a specific call or put to
buy, with every reason visible. Recommendations can be paper-traded with one click; real
orders are always placed by the trader in their broker's app. TradeDisha never places an
order.

## Status

Milestone 0 complete: backend and frontend skeletons run and talk to each other, with the
full lint, type and test toolchain in place. See [docs/plan.md](docs/plan.md) for what
comes next.

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

Open http://localhost:5173. The top bar shows the backend status and a theme toggle.

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
config/     tunable signal parameters (from Milestone 3)
docs/       intent, plan, spec, data dictionary
scripts/    check.sh
```
