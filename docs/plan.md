# TradeDisha — Development Plan

Requirements live in [intent.md](intent.md). This plan breaks the first version into
milestones. Every milestone ends with something that runs and can be looked at, so the
direction can be corrected early rather than at the end.

## Approach

- **Iterative.** Each milestone delivers a thin, working slice from data to screen. Later
  milestones deepen the slice rather than adding new layers that cannot yet be seen.
- **Test-first.** Indicator maths, signal rules, and paper-trade exits are written against
  tests before the code, using recorded market data so they can run outside market hours.
- **Record early, replay always.** The first milestone with a live feed also records it.
  From then on, every later milestone can be developed and demonstrated on a replay of a
  real session, independent of market hours or the daily broker login.
- **Provider behind an interface.** Upstox is the chosen feed, but all market data enters
  through one adapter so that the provider can be swapped (Angel One SmartAPI is the free
  fallback) without touching the rest of the system.

## Quality bar (applies to every milestone)

| Quality | Target | How it is checked |
|---|---|---|
| Latency | tick arrival at app to painted < 250 ms p95 (broker→app hop reported separately); detected minute close to bias/signal painted < 100 ms p95; UI frame time < 16 ms while the chain is updating | built-in latency metrics from Milestone 1; measured in every milestone demo |
| UI | dark trading-terminal default, light toggle; no jank, no flicker, no manual refresh | visual check each demo; frame-time overlay in dev |
| Clean code | ruff + mypy strict + pre-commit on backend; ESLint strict + Prettier + `tsc --noEmit` on frontend; tests for all trading logic | CI-style check script runs green before a milestone is called done |
| Tunability | every signal-shaping parameter in one TOML file; "Reload config" in the app validates and applies it at the next minute | Milestone 3 onward |

## Stack (decided)

- Backend: Python 3.12 managed with uv; FastAPI + uvicorn (uvloop, orjson); websockets and
  httpx for the broker; SQLite via SQLAlchemy Core; numpy for indicators; pytest,
  hypothesis; ruff, mypy, pre-commit.
- Frontend: Vite + React + TypeScript (strict); TanStack Query; Zustand for live stores;
  TradingView `lightweight-charts`; TanStack Virtual for the chain; Tailwind with a
  design-token theme; ESLint, Prettier, Vitest, Playwright.
- Layout: `backend/` and `frontend/` under the repository root; `docs/` for intent, plan,
  and design notes.

## Prerequisite (owner: Anuj)

Open an Upstox account and register an API application to obtain an API key, secret, and
redirect URI. Milestone 1 can be built without these, but cannot be verified live.

---

## Milestone 0 — Skeleton that runs

**Goal:** a repository that starts, with both halves talking to each other.

- Backend project initialised with uv; FastAPI app with a health endpoint.
- Frontend project initialised with Vite; dark/light theme tokens and app shell; one page
  that calls the health endpoint and shows the result.
- `.env.example`, README with setup steps, `docs/` folder with intent, plan, and spec.
- Tooling wired: ruff, mypy strict, pre-commit, ESLint, Prettier, Vitest; one `check`
  script runs all of them plus `uv run pytest` (one trivial test).

**Demo:** `uv run uvicorn` plus `npm run dev` shows a page saying the backend is up.

---

## Milestone 1 — Live feed on screen, and recorded

**Goal:** real NIFTY and BANK NIFTY ticks flowing from Upstox into the browser, and saved
to disk for replay.

- Upstox OAuth login flow; token stored; health endpoint reports login status.
- Daily instrument master download; resolution of spot, current-month futures, nearest
  expiry (weekly NIFTY, monthly BANK NIFTY), and ATM ± 10 strikes.
- Websocket feed adapter: subscribe, decode, reconnect with backoff, emit normalised ticks.
- Tick persistence to SQLite, plus a replay provider that reads them back at real or
  accelerated speed.
- Browser: top bar with market status, feed health and tick age, Login button; a raw
  ticking price for each index.
- Latency instrumentation: every tick carries exchange, ingest, and send timestamps; the
  client records receive time; `/api/metrics` and a dev overlay show p50/p95 per hop.

**Demo:** during market hours, log in and watch the two index prices tick live with the
latency overlay under 250 ms p95. After hours, replay the recorded session and see the same.

**Risk retired:** Upstox websocket format, rate limits, and subscription limits are
confirmed against reality.

**Status (2026-11-12):** built and demoed on the synthetic provider. Provider interface,
synthetic and replay feeds, instrument resolution against a generated master, tick
recording, WebSocket push, latency instrumentation and the top bar are done. **Deferred
until an Upstox account exists:** the OAuth login flow, the real instrument-master
download, and the Upstox websocket adapter. These slot in behind the existing
`MarketDataProvider` interface and `AuthService` without touching the rest.

---

## Milestone 2 — Option chain panel

**Goal:** the right-hand panel of the final screen, live.

- In-memory chain state per index built from ticks and the option-chain REST snapshot.
- Opening OI captured at start (or backfilled when started late).
- Derived values: ATM strike, PCR, OI change since open and since previous minute,
  max pain. Tested against recorded chain snapshots.
- Re-centring of the subscribed strike window when spot moves two or more strikes.
- Browser: option chain table with CE and PE price, change, OI, OI change, IV; ATM row
  highlighted; OI build-up shaded; PCR and max pain in the panel header. Index tabs.

**Demo:** switch between NIFTY and BANK NIFTY and watch the chain update tick by tick.

**Risk retired:** whether Upstox delivers IV on the feed. If not, decide between local
Black-Scholes IV or dropping IV indicators from v1.

---

## Milestone 3 — Candles, chart, and market view

**Goal:** the main area shows the index chart and a live bullish/bearish meter with its
evidence.

- 1-minute candle builder from ticks; backfill of today's candles from Upstox on late
  start; candles persisted.
- Indicators as pure functions with unit tests on synthetic candles:
  - Price trend: EMA 9/21 crossover, spot vs VWAP (futures), supertrend (10, 3).
  - OI structure: PCR, ATM ± 2 OI change classification, max-pain drift.
  - Premium behaviour: ATM CE vs PE premium momentum, ATM IV change, premium/spot
    confirmation.
- Weighted aggregator (0.40 / 0.35 / 0.25) producing bias and strength every minute,
  during market hours only. Indicator values persisted.
- **Tunable config file**: all signal-shaping parameters in `config/params.toml`;
  validated on load; "Reload config" in the top bar re-reads it and
  applies at the next minute close, or reports the validation error and keeps the old
  values.
- Browser: candlestick chart with EMA and VWAP overlays; bias meter; evidence breakdown
  table showing each indicator's score, weight, and contribution.

**Demo:** replay a recorded session and watch the meter move with the market, with every
vote visible; change a weight in the config file, click Reload, and see the meter respond
the next minute.

**Review point:** look at a few days of bias history against what actually happened and
adjust weights in the config file before building signals on top.

---

## Milestone 4 — Signals

**Goal:** the app issues recommendations with entry, target, stop, and reasons.

- Signal lifecycle: fire when |bias| ≥ threshold (default 0.5) and no signal is active on
  that index; lapse after five minutes untraded, or end on bias reversal / return to
  neutral; a fresh signal fires the next minute if bias is still beyond threshold; open
  paper trades never block signals; no new signals after 15:00.
- Signal content: index, exact option, entry at ATM LTP, target +30%, stop −15%,
  timestamp, full evidence breakdown.
- Expiry-day mode: expiring contract traded all day; target and stop in index points
  (40/20 NIFTY, 100/50 BANK NIFTY) converted via delta; no new signals after 13:00; OI
  weight halved; breakdown flags expiry day.
- Signals persisted. Tests cover fire, lapse, reversal, time cut-offs, expiry-day rules,
  and config reload mid-session.
- Browser: active signal card with time-left countdown; signal markers on the chart;
  signal history list.

**Demo:** replay a volatile session and see signals fire and lapse with reasons.

---

## Milestone 5 — Paper trading and journal

**Goal:** one-click paper trades tracked to exit, with a journal that answers "is this
worth real money?"

- Paper trade opens only on click, at current LTP, recording slippage vs signal entry.
- Tick-driven exits: target, stop, 15:15 square-off, manual close.
- Gross and net P&L with configurable per-trade cost (default ₹60 round trip per lot).
- Signals while trades are open: any new signal's card highlights the open trades' key
  facts; an open trade shows "bias reversed" whenever the bias opposes it, clearing when it
  no longer does.
- Feed-down handling: no paper trade opens without a live price; exits re-evaluate from
  the first tick after a gap and are marked `after_gap`; square-off at 15:15 with the feed
  down uses the last known price and is marked `stale`.
- Journal page: trade list and summary stats (hit rate on net P&L, average win/loss, net
  result, overall and per index).
- Tests cover every exit path, slippage, cost netting, fill-quality marking, and signals
  firing while trades are open.

**Demo:** full loop on a live session: signal fires, click Paper trade, watch it to exit,
see it in the journal.

**This completes the first version as described in intent.md.**

---

## Milestone 6 — Hardening for daily use

**Goal:** the app survives a real trading week without babysitting.

- Clear degraded states: login missing or expired, feed disconnected, market closed,
  holiday calendar.
- Startup after market open handles backfill and opening-OI correctly every time.
- Reconnect, re-subscribe, and re-centre are exercised by fault-injection tests on replay.
- Log and surface feed gaps so stale data is never shown as live.
- Full-day soak on replay at 1× speed: memory flat, latency p95 within budget at 15:29 as
  at 09:16, no UI frame drops with the chain updating.
- Tick pruning: a Data panel that deletes raw ticks up to and including a chosen date
  after showing the day count and size to be freed; derived tables untouched; the database
  is vacuumed afterwards.
- Frontend production build served by the backend so it starts with one command.

**Demo:** start late, kill the network, restore it, and the dashboard recovers without a
restart or a misleading screen.

---

## After the first version

Not planned in detail yet; listed so the design keeps room for them.

1. **News and FII/DII inputs** as additional evidence groups with their own slower pollers.
2. **Replay and tuning tools**: step through a past day, change weights, see how signals
   would have changed.
3. **Back-testing** over the stored history.
4. **Further instruments**: FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX, then stock options.

## Working agreements

- Each milestone starts with a short written note of what will be built and ends with a
  demo against the goal above; anything that fails the demo is fixed before moving on.
- Defaults chosen by the builder (weights, thresholds, strike width, costs) are kept in one
  configuration file and listed in the README, so they are visible and easy to change.
- No real-order code path is ever added, even behind a flag.
