# TradeDisha

A personal trading assistant for NSE index options (NIFTY and BANK NIFTY). It watches the
market live through a broker data feed, forms a bullish/bearish view every minute from
price trend, open interest, and premium behaviour, and recommends a specific call or put to
buy, with every reason visible. Recommendations can be paper-traded with one click; real
orders are always placed by the trader in their broker's app. TradeDisha never places an
order.

## Status

Design phase. No code yet. The documents below are the source of truth for what gets built.

## Documents

| File | What it is |
|---|---|
| [docs/intent.md](docs/intent.md) | Requirements: purpose, scope, behaviour, qualities. No technical detail. |
| [docs/plan.md](docs/plan.md) | Development plan: iterative milestones, each ending in a runnable demo. |
| [docs/spec.md](docs/spec.md) | Architecture and detailed design: components, data model, indicators, signal engine, API, frontend, performance budget, code standards. |
| [docs/dd.md](docs/dd.md) | Data dictionary: every domain and technical term used above. |

## Planned stack

- Backend: Python 3.12 (uv), FastAPI, asyncio, SQLite.
- Frontend: Vite, React, TypeScript, TradingView lightweight-charts.
- Data: Upstox API v2 (free with an Upstox account).

Setup instructions will be added with Milestone 0.
