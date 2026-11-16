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
| Tunability | every signal-shaping parameter editable in the app, validated, applied at the next minute and kept as numbered versions (`config/params.toml` only seeds a new database) | Milestone 3 (file and reload), replaced by C1 (versions in the database) |

## Stack

As built (the source of truth is `backend/pyproject.toml` and `frontend/package.json`):

- Backend: Python 3.12 managed with uv; FastAPI + uvicorn; `websockets`, `httpx` and
  `protobuf` for the broker; SQLite through the standard `sqlite3` module; pure-Python
  indicator maths; pytest, hypothesis; ruff, mypy strict, pre-commit.
- Frontend: Vite + React 19 + TypeScript (strict); Zustand for live stores; plain `fetch`
  for REST; TradingView `lightweight-charts`; Tailwind v4 with a design-token theme;
  ESLint, Prettier, Vitest.
- Layout: `backend/` and `frontend/` under the repository root; `docs/` for intent, plan,
  spec, signal walkthrough, enhancements and the data dictionary.

Planned at the start and **not adopted**: orjson, SQLAlchemy Core, numpy, TanStack Query,
TanStack Virtual, import-linter, Playwright and OpenAPI-generated types. Each turned out
unnecessary at this size (the chain is 21 rows; the indicator windows are a few hundred
bars).

## Prerequisite (owner: Anuj)

Open an Upstox account and register an API application to obtain an API key, secret, and
redirect URI. Milestone 1 can be built without these, but cannot be verified live. (Done:
the live feed has been in daily use since 2026-11-13.)

## Milestones at a glance

In the order they were built. The sections below keep their original grouping (first
version, then enhancements, configuration and signal quality).

| Milestone | What | Built | Status |
|---|---|---|---|
| 0–4 | Skeleton, live feed, option chain, candles and bias, signals | 2026-11-12 | built; demoed on synthetic, now in daily use on the live feed |
| 5 | Paper trading and journal | 2026-11-13 | built |
| 6 | Hardening for daily use | 2026-11-13 | built; demo and soak run |
| E1 | Layout, dates and index details | 2026-11-13 | built; checked on the live feed |
| S1 | Signal yardstick and order-flow recording | 2026-11-13 | built |
| S2 | Order-flow trigger, in shadow | 2026-11-14 | built; waiting for shadow data |
| E2 | Minimisable panels | 2026-11-13 | built; checked in a browser |
| E3 | Re-ordering the main column | 2026-11-16 | built; checked on the live feed |
| C1 | Editable, versioned config | 2026-11-16 | built; checked in a browser |
| E4 | BULLION tab | 2026-11-16 | built; checked on the live feed |
| E5 | NSE and MCX hours apart | 2026-11-16 | built; checked on the live feed |
| E6 | Bullion signals and paper trades | 2026-11-16 | built; bias and panels checked live, a live bullion trade still to see |
| E7 | Live signal levels | 2026-11-16 | built, with unit tests |
| E8 | Net volume per candle | 2026-11-16 | built, with unit and replay tests |
| S3 | Switch the trigger on, on evidence | — | planned: after five live sessions of shadow data |

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

**Status (2026-11-12):** built and demoed on the synthetic provider, which supplies IV
and OI per option. Chain state with PCR, OI change (since open and since previous minute),
max pain and build-up classification; per-minute persistence to `chain_minutes`;
re-centring with live subscribe/unsubscribe; `/api/chain/{index}` and `chain` WS frames;
the panel with index tabs. **Still open for Upstox:** whether IV/delta arrive on the real
feed (the Black-Scholes fallback in spec §7.3 stays planned) and opening-OI backfill from
the option-chain REST snapshot; until then OI change is measured from the first tick seen,
which equals market open when the app starts before 09:15.

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
  values. *(Replaced in Milestone C1 by versions edited in the app; the file now only
  seeds a new database.)*
- Browser: candlestick chart with EMA and VWAP overlays; bias meter; evidence breakdown
  table showing each indicator's score, weight, and contribution.

**Demo:** replay a recorded session and watch the meter move with the market, with every
vote visible; change a weight in the config file, click Reload, and see the meter respond
the next minute.

**Review point:** look at a few days of bias history against what actually happened and
adjust weights in the config file before building signals on top.

**Status (2026-11-12):** built and demoed on the synthetic provider. Candle builder with
gap fill and stale flush, `candles_1m` and `bias_minutes` persisted, nine indicators as
pure functions with unit and property tests, aggregator with expiry-day reweighting,
`config/params.toml` with validation and `POST /api/parameters/reload`, chart with
overlays, bias meter and evidence table. Two deliberate deviations from the spec: the bias
is computed on every minute close regardless of market status (signal firing is what
market hours gate, in Milestone 4), and indicators recompute over the stored candle window
(at most 400 bars) rather than incrementally, which measures in microseconds and keeps
them pure. Late-start candle backfill belongs to the Upstox adapter.

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

**Status (2026-11-12):** built and demoed on the synthetic provider. SignalEngine with
fire / lapse / reverse / traded lifecycle, open trades never gate, re-arm hysteresis knob
(off by default), hours and feed-live gates, expiry-day point targets converted through
feed delta or Black-Scholes delta, `signals` table (migration 004), REST and WS frames,
a gate reason per index so the card can say why nothing fired. Signal hours are enforced
for replay and Upstox feeds and skipped for the synthetic feed. The Paper trade button is
rendered disabled until Milestone 5.

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

**Status (2026-11-13):** built. `PaperTradeManager` opens only from `POST /api/paper-trades`
(the Paper trade button), at the current LTP, and closes on target, stop, square-off or
manual close, recording fill quality (`live`, `after_gap`, `stale`). Trades left open by a
restart are picked up again (as a gap); trades left open overnight are squared off `stale`
at the last recorded price on the next start. Cost per trade is fixed at entry. The
dashboard shows open trades with live P&L and the bias-reversed flag; the Journal page
lists trades with filters and summary cards. Unit tests cover every exit path; the
end-to-end run is manual. **Not built:** paper-trade entry/exit markers on the price chart
and click-through from a journal row to the signal's evidence.

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

**Status (2026-11-13):** built. The demo and the full-day soak have since been run by the
owner.
- Degraded states: `/api/health` carries one `banner` (login missing/expired, feed not
  started, feed gap with "since", holiday, pre-open, market closed); the UI shows it under
  the top bar and dims last-known data. A lost backend connection is shown the same way.
- Late start (Upstox): today's 1-minute candles for spot and futures are fetched and
  seeded, chart overlays rebuilt, and opening OI taken from the option-chain snapshot's
  previous-close OI (`oi_baseline` is `partial` until every leg has one). Strikes added
  by a re-centre get a baseline too. Each part can fail on its own and is logged.
- Feed gaps: detected by the half-second timer and from tick timestamps; written to
  `feed_events` (`feed_gap_start`/`feed_gap_end`/`feed_gap`) with the duration; open paper
  trades are marked so their next exit is `after_gap`.
- Fault injection: `TRADEDISHA_REPLAY_DROP` withholds time ranges on replay; a test replays
  an outage plus a re-centre and checks the log and the re-subscription.
- Tick pruning: `GET /api/data/usage`, `POST /api/data/prune-ticks`, and the Data panel
  with a typed-date confirmation; batches of 50k, then incremental vacuum.
- One command: `make start` builds the web app and the backend serves it.
- **Not done:** the full-day 1x soak (memory, latency at 15:29, frame drops) has not been
  run. Backfill responses are parsed as documented by Upstox and are unverified live.

---

## Enhancements

Improvements requested after release 1.0.0. The running list, including items left for
later, is in [enhancements.md](enhancements.md); requirements are in intent.md under
"Enhancements after the first version".

## Milestone E1 — Layout, dates and index details

**Goal:** the screen fits how the trader works: panels sized to taste, dates in the
familiar format, and the day's key index facts one click away.

- **Dates as DD/MM/YYYY.** One `fmtDate` helper; used in the journal, on every expiry
  shown (tiles, signal card, chain header), the replay day in the top bar and the Data
  panel. The Data panel's typed confirmation takes the date as displayed. Dates stay ISO
  in the API, the config file and file names.
- **Resizable layout.** A draggable divider between the main column and the option chain,
  and one under the price chart for its height. Size limits, keyboard control,
  double-click to reset, sizes remembered in the browser and re-clamped when the window
  changes. The chart resizes with its container.
- **Hideable right-hand panel.** A hide button on the option-chain panel and a narrow
  strip to show it again; remembered in the browser. Data keeps flowing while hidden.
- **Index statistics (backend).** India VIX added to the subscription set; one year of
  daily candles fetched per index at start for the 52-week range; `IndexStats` computed
  per index (day open/high/low, range position, previous close and change, 52-week
  high/low including today, futures premium, VIX); `GET /api/stats/{index}`, `stats` in
  the WebSocket `hello`, and a `stats` frame at most once a second.
- **Index details view.** A collapsible section under the index summary showing those
  statistics in five groups, closed by default, state remembered, "—" for anything the
  current feed cannot supply. Works for NIFTY and BANK NIFTY through the tabs.
- Tests: date formatting (ISO string and epoch ms, IST day boundary); layout clamping,
  persistence and reset; statistics maths (range position incl. high = low, 52-week range
  widened by today's extreme, premium, missing inputs); daily-candle parsing against a
  mocked response and its failure path; the details view with full and with missing data.

**Demo:** drag both dividers, reload, and find them where they were left; hide the
option-chain panel, reload, and find it still hidden, then show it at its previous width; every date on
the dashboard, journal and Data panel reads DD/MM/YYYY; on the live feed open the details
view for each index and compare day and 52-week figures and VIX with NSE's own.

**Risk retired:** whether 52-week figures derived from daily candles match NSE's, and
whether India VIX ticks on the feed like the other indices (spec §17).

**Not in E1:** zoom-in and zoom-out buttons on the charts (deferred).

**Status (2026-11-13):** built, and since checked by the owner on the live feed, including
the 52-week figures against NSE's and India VIX ticking. All four parts are in place with
unit tests. Two things differ from, or add to, the note above: previous close
is now stored with recorded ticks (once per instrument when it changes), so a replayed day
shows change on the day — days recorded before this have none; and the details toggle
shows the day's change beside it while closed. The two risks above were closed on the
live feed.

**Design:** spec §6.2 (VIX), §6.5 step 3 (52-week fetch), §7.4 (index statistics),
§12 (API), §13.2–13.4 (details view, resizable layout, date format, preferences).

## Milestone E2 — Minimisable panels

**Goal:** the trader can tuck any panel away so the others get the room, and bring it
back where it was, without missing a signal or an open trade.

- **Panel frame.** One shared frame around all eight panels (index, market view, signal,
  open paper trades, price chart, evidence, signals today, option chain) with a title bar
  and a minimise button. No new library.
- **Minimise.** Collapses to the title bar in place with a one-line summary; panels below
  move up; remembered in the browser. The option chain's minimised form is the existing
  strip on the right edge, and E1's remembered choice carries over. The chart keeps its
  zoom while minimised.
- **Opens itself.** A minimised signal or open-trades panel expands for a new signal or
  newly opened trade, once.
- **Restore panels** button in the top bar while anything is minimised.
- **Open paper trades panel** always on the page (it says so when none are open) and
  moved to second last in the main column, just above signals today.
- Tests: panel state (parse, E1 carry-over, toggle, two panels opened in the same moment,
  restore all); open-on-new (once per id); each one-line summary with full and missing
  data; the frame expanded and minimised with its labels; the top-bar button; the open
  paper trades panel with none open.

**Demo:** minimise each panel and see its summary and the panels below move up; reload to
find them still minimised; expand them one by one and with "Restore panels", finding
sizes and chart zoom as they were; on a replayed day, minimise the signal card and see it
open on the next signal, and the open-trades panel on the next paper trade.

**Not in E2:** full screen for a panel (built first, then removed at the owner's request
the same day); dragging panels to re-order or re-dock them; chart zoom buttons (still
deferred).

**Status (2026-11-13):** built, with unit tests, and checked in a browser on the synthetic
feed: minimise, summaries, reload, expand, "Restore panels", the chart recovering its
size, and the open paper trades panel in its place with none open. The demo on a live day
has since been run by the owner.

**Design:** spec §13.2 (PanelFrame, SidePanel).

## Milestone E3 — Re-ordering the main column

**Goal:** the trader can put the panels of the main column in the order that suits them.

- **Move buttons.** Up and down arrows on the title bar of each main-column panel, beside
  minimise; the one with nowhere to go is disabled. No new library.
- **Six units.** Index; market view with signal; price chart with its height divider;
  evidence; open paper trades; signals today. Market view and signal move as one, from
  either title bar, and keep sharing a row.
- **Remembered** in the browser. "Restore panels" also puts the default order back, and
  shows while the order is not the default.
- Fixed: the index tabs at the top, the option chain in its own column.
- Tests: reading a stored order (unknown, repeated and missing ids); moving a unit and the
  ends; the pair moving together; two moves in the same moment; restore; the frame's move
  buttons, disabled ends and the pair's label.

**Demo:** move the chart to the top, the market view and signal pair below evidence, and
signals today up twice; reload to find the order kept; "Restore panels" to get the
default back.

**Not in E3:** drag-and-drop; swapping market view and signal within their row; moving the
option chain.

**Status (2026-11-16):** built, with unit tests, and the demo run in a browser on the
live feed, including the chart keeping its zoom and height divider when moved.

**Design:** spec §13.2 (Panel order).

## Milestone E4 — BULLION tab

**Goal:** gold and silver on their own tab beside NIFTY and BANKNIFTY, with what Upstox
already provides.

- **Contracts.** MCX `GOLD` and `SILVER`, near and next month, picked each day from
  Upstox's MCX instrument file and rolled on expiry day. Upstox has no spot price.
- **The tab.** A card per metal:
  - LTP and change on the day
  - day open, high, low and position, previous close, ATP
  - volume, OI, bid and ask with quantities and spread, buy vs sell quantity
  - the contract's one-year high and low, circuit limits
  - the next-month price and calendar spread

  Below the cards: the gold/silver ratio, and a 1-minute chart with VWAP and a metal
  switch. The option chain is hidden on this tab.
- **Display only.** Not recorded, not replayed, no part in the bias or signals. Live feed
  only; any failure leaves the tab out and the index feed untouched.
- Tests:
  - backend: parsing real-shaped MCX records (minis and petals excluded); near and next
    month including expiry day; the once-a-day download and its failure; the `1d` OHLC
    decode; the full quote from a recorded real answer; the snapshot maths (ratio, spreads,
    range, fallbacks); the VWAP series; the tracker (day range, candles, next month);
    ticks kept out of `ticks`; the REST routes and the three WebSocket frames
  - frontend: the cards, the ratio and the chart switch; the store keeping BULLION
    selected

**Demo:** log in on a trading day (MCX is open until 23:30), open BULLION, and compare
GOLD and SILVER with the Upstox app: price, day range, ATP, OI, circuit limits, next
month. Switch the chart; reload to find the tab and switch kept.

**Status (2026-11-16):** built, with unit tests, and checked by the owner on the live feed.

**Design:** spec §6.6 and §13.2 (IndexTabs, BullionView).

## Milestone E5 — NSE and MCX hours apart

**Goal:** bullion keeps MCX hours, and gold ticking never hides an index outage.

- **Index liveness from NSE ticks only.** Before, any tick kept the feed "live", so an
  index feed gone quiet while MCX ticked never entered degraded mode.
- **MCX hours and calendar.** `mcx_open`/`mcx_close` settings and
  `config/mcx-holidays.txt` (full holidays and evening-only days); a second `MarketClock`
  on the same time source.
- **Bullion status** (`live`, `stale`, `closed`, `holiday`) in the health frame; MCX
  outages logged as `bullion_gap_start`/`bullion_gap_end`; display only.
- **Banner on the BULLION tab** follows MCX: no NSE "Market closed" after 15:30, a stale
  warning when bullion stops.
- **Top bar follows the tab.** On BULLION the market pill reads MCX status and the feed
  pill's tick age is the newest bullion tick. A closed market's silence is shown muted,
  not red.
- **Session banners stand out.** Closed, holiday and pre-open (NSE and MCX) are an amber
  band with a bold title; errors stay red.
- **Data dictionary.** Bullion and MCX terms (dd §1a), with the NSE-only entries marked.
- Tests: MCX clock through the day, late opens, holidays, calendar parsing; bullion ticks
  not keeping a silent index feed live; an MCX outage at 20:00 logged without touching
  index state; bullion status by MCX hours; the health field; the banner on the tab;
  the top-bar pills by tab and hours; the amber titled session banner.

**Demo:** on the live feed after 15:30, the index tabs say "Market closed" and BULLION
shows live prices with no banner. Drop the network for half a minute: BULLION says prices
are stale from the last tick, and `feed_events` has the bullion gap rows.

**Status (2026-11-16):** built, with unit tests, and checked on the live feed: the closed
banner, the top-bar pills by tab, and a network drop on BULLION while MCX was open.

**Design:** spec §6.6 (Hours and liveness) and §14.

## Milestone E6 — Bullion signals and paper trades

**Goal:** gold and silver get their own market view, signals and paper trades, on MCX
hours, without touching the index engines.

- **Bias:** trend only (EMA cross, VWAP position, supertrend) on the near-month candles,
  worked out `bullion.eval_offset_seconds` (20 s) after each minute close.
- **Signals:** buy or sell the near-month future (`BUY_FUT` / `SELL_FUT`) at the bullion
  entry threshold, with target and stop a % of price; gates for MCX hours (09:15–22:45),
  bullion liveness and a switch to turn them off.
- **Paper trades:** long or short, ₹ per point from `qty_multiplier` (GOLD 100, SILVER 30),
  cost fixed + % of value, square-off 23:00 on the MCX clock; a separate manager that owns
  only bullion trades.
- **Journal:** GOLD, SILVER and a bullion total; "overall" is index options only.
- **Recording:** `bullion_ticks` (migration 011) and bullion candles; a bullion replay
  (`TRADEDISHA_REPLAY_BULLION`).
- **UI:** on BULLION, the charted metal's market view, evidence, signal card with
  Paper-trade, open trades and chart markers; FUT long/short labels everywhere.
- Tests: the parameters; trend-only aggregation (bounds by hypothesis); the bias engine and
  its offset; the signal lifecycle and every gate; short P&L, target and stop; point value
  and cost; MCX square-off; ownership on restore; journal scopes; the API round trip;
  recording; a replayed evening firing at the offset; the frontend labels and tab.

**Demo:** on a trading evening, open BULLION: see each metal's bias and evidence; when a
signal fires, paper-trade it and follow it to target, stop or the 23:00 square-off; find it
under Bullion in the Journal with "Index options" unchanged. The next day, replay the
evening with `TRADEDISHA_REPLAY_BULLION=true TRADEDISHA_REPLAY_SPEED=0`.

**Status (2026-11-16):** built, with unit and replay tests. On the live feed the bullion
bias, evidence and panels (same order and controls as the index tabs) were checked; no
bullion signal had fired yet, so a live paper trade is still to be seen.

**Design:** spec §6.6, §9a, §10, §13.2.

## Milestone E7 — Live signal levels

**Goal:** while a signal waits for the trader, its entry, target and stop follow the
price, and a paper trade gets the levels that were on screen.

- The fired levels stay on the signal (history, scoring). The live ones apply the same rule
  to the current price: percentage signals keep their ratios; expiry-day signals re-apply
  their index points through the option's current delta. Bullion futures, long or short,
  the same way.
- `SignalOut.live`, and a `signal_live` frame once a second while any signal is active.
- The signal card shows a Fired row and a Live row (with how far the entry has moved).
- A paper trade's target and stop are the live levels at its fill, no longer the fired ones.
- Tests: the re-scaling rule (ratios, the 5-paise floor, points via delta, a put's delta);
  live levels from the chain and from the bullion tracker; paper trades from the fill
  (index and bullion); the API field and the per-second frame; the store never reviving an
  ended signal; the card's two rows.

**Demo:** wait for a signal, watch the Live row move with the option, click Paper trade and
see the trade's target and stop match the Live row.

**Status (2026-11-16):** built, with unit tests.

**Design:** spec §9.3, §10.1.

## Milestone E8 — Net volume per candle

**Goal:** see, minute by minute, whether buyers or sellers drove the traded volume.

- Upstox sends no buy/sell split, so each tick's volume is signed in the candle builder:
  quote rule against the quote before the tick, tick rule for prints between bid and ask.
  Candles keep buy and sell volume (`candles_1m.bv` / `sv`, migration 012); `None` where
  there is no side information (index spot, backfilled minutes).
- The API's candles carry `bv` / `sv`, and the index candles response adds the near-month
  future's candles (`fut_candles`); the future's `candle` frames are kept by the store.
- The price chart gets a second pane: a net-volume histogram (green buying, red selling)
  from the near-month future, or the metal's future on BULLION, with net, buy and sell for
  the minute under the crosshair.
- Display only: not an input to the bias or the signals.
- Tests: the trade-side rule (quote and tick rule cases); the builder signing against the
  quote before the tick, resetting each minute, gaps and no-volume series; storage and
  migration; replay rebuilding the same split; the API, the future's candle frame and the
  bullion candles; the frontend bar and legend helpers and the store.

**Demo:** on a live or replayed day, NIFTY, BANK NIFTY and BULLION show the histogram under
the chart; hover a minute for its buy, sell and net volume. Backfilled minutes from before
the app started have no bar.

**Status (2026-11-16):** built, with unit and replay tests; checked in a browser on the
synthetic feed.

**Design:** spec §7.1, §11, §12, §13.2.

## Milestone C1 — Editable, versioned config

**Goal:** the trader tunes the parameters in the app, can always get back to an earlier
set, and can see which set produced each signal.

- **Versions in the database.** Table `config_versions` (migration 010); the highest
  version is in force; a new database takes version 1 from `config/params.toml`.
- **Edit.** A form in the Config control built from a field list the server describes
  (kind, limits, help). A save needs a tag and a change, is validated as a whole, and
  applies from the next minute close.
- **History and revert.** Every version listed; reverting saves the old values as a new
  version.
- **Signals carry the version** (`signals.config_version`), shown as a chip on the signal
  card and in "Signals today"; hovering it shows that version's values, with those that
  differ from the config in force highlighted.
- "Reload config" and `POST /parameters/reload` are removed.
- Tests: the service (seed, save, tag and no-change refusals, revert, a stored version
  the model no longer accepts, surviving a restart); the field list; the stamp on live
  signals; the six routes and the websocket frame; the editor (save, server errors,
  discard, new version resets the form), history and revert; the chip and its panel.

**Demo:** change the entry threshold and save with a tag; see the version in the top bar
and in History; try an invalid value and see it refused; wait for a signal and hover its
chip; revert to version 1; restart and find the history intact.

**Not in C1:** scorecard split by config version; comparing two versions; scoring a stored
version offline.

**Status (2026-11-16):** built, with unit tests, and the demo run in a browser on the
synthetic feed with a scratch database.

**Design:** spec §3.2 (Versions), §12, §13.2 (Config control, ConfigVersionChip).

---

## Milestone S1 — Signal yardstick and order-flow recording

**Goal:** know how good the signals are, and start recording what the trigger will need,
without changing a single signal.

- **Record the order-flow fields** of the Upstox `full` feed with every tick: best-level
  and five-level bid and ask quantities, total buy and sell quantity, exchange average
  price, last traded quantity. Synthetic feed generates them too.
- **Score every signal** (spec §9.5): target first, stop first or neither within the
  horizon; best and worst price; price after 1, 5 and 15 minutes; lateness from the spot
  move before and after firing. The ask and spread at firing are stored on the signal.
- **Scorecard:** `GET /api/signals/scorecard`, an outcome column and a day line in
  "Signals today", and the headless tool `tradedisha.tools.score` that replays recorded
  days in a scratch database with any parameter file.
- Tests: feed decoding and storage of the new fields; the tracker (each result, horizon,
  square-off cut, marks, spot moves, restart); scorecard arithmetic; the API; the tool
  leaving the recorded database untouched; the history column.

**Demo:** replay a recorded day; every signal in "Signals today" shows target, stop or
neither with its best and worst move; the tool prints the same numbers for that day.

**Status (2026-11-13):** built, `make check` green. The tool was run on the day recorded
live on 2026-11-13 (one signal: stop first, lateness 0.95). Not yet done: a live session,
which is what will confirm that the order-flow fields arrive and show how much the
database grows (spec §17); the demo in a browser on a replayed day.

**Design:** spec §6.2, §9.5, §11, §12.1, §13.2 (SignalHistory).

## Milestone S2 — Order-flow trigger, in shadow

**Goal:** see, on real days and without risk, whether "setup, then trigger" beats the
minute-close rule.

- **Flow score** per index from the future and the ATM call and put: five-level book
  imbalance, `tbq`/`tsq` imbalance, and traded volume signed by where it printed against
  the quote; smoothed over a few seconds; timed by tick timestamps.
- **Trigger rule:** a setup while the last minute-close `|bias| ≥ setup_threshold`
  (default 0.35); fire when the flow score agrees for `hold_seconds` and the option's
  spread is within `max_spread_pct`; entry at the ask. Hours, feed-live, one active per
  index, re-arm, TTL and reversal as today. New gate reasons: no setup, flow not
  confirmed, spread wide.
- **Shadow engine:** a second signal engine runs whichever rule is not live. Its signals
  are stored and scored but never shown as active and cannot be paper-traded.
  `signal.entry_mode` (default `minute_close`) picks the live rule.
- Scorecard split by rule; a flow line under the evidence table; shadow signals greyed in
  "Signals today".

**Demo:** on the synthetic feed and one live day, shadow trigger signals appear beside the
real ones with outcomes, and the scorecard shows a row for each rule.

**Status (2026-11-14):** built, `make check` green. Seen in a browser on the synthetic
feed: the flow line, shadow trigger signals greyed beside the live ones with outcomes,
both count lines, a scorecard row per rule, and a paper trade on a shadow signal refused.
That run used a trial parameter file (bias on trend only, lower flow bar), because the
synthetic option chain is random and never builds a bias on the shipped values; it shows
the mechanism, not that the rule is any good. Not yet done: a live day.

The scoring tool on the day recorded on 2026-11-13, shipped parameters. That day has no
book quantities, so the flow score came from signed trades alone:

| rule | signals | target first | stop first | neither | avg best | avg worst | lateness |
|---|---|---|---|---|---|---|---|
| minute_close (live) | 1 | 0 % | 100 % | 0 % | +0.6 % | −21.4 % | 0.95 |
| trigger (shadow) | 14 | 0 % | 42.9 % | 57.1 % | +8.0 % | −12.0 % | 0.48 |

One day and untuned values: the trigger fired earlier in the move and far more often, and
nothing reached its target under either rule. Not evidence either way.

**Design:** spec §8.5, §9.6, §12, §13.2.

## Milestone S3 — Switch on, on evidence (planned)

- After at least five live sessions recorded with S2, compare the two scorecard rows and
  tune the flow parameters and `setup_threshold` with the headless tool.
- If the trigger reaches target first more often and fires earlier, set
  `signal.entry_mode = "trigger"`; the minute-close rule then runs as the shadow. If not,
  nothing has changed for the trader.
- Signal card: texts for the new gate reasons; entry shown as the ask, with the spread
  (already built with S2).

---

## After the first version

Not planned in detail yet; listed so the design keeps room for them.

1. **News and FII/DII inputs** as additional evidence groups with their own slower pollers.
2. **Replay and tuning tools**: step through a past day, change weights, see how signals
   would have changed. (Partly there: `tools/score.py` replays recorded days with trial
   parameters and prints the scorecard.)
3. **Back-testing** over the stored history.
4. **Further instruments**: FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX, then stock options. (MCX
   gold and silver were added in E4/E6.)

## Working agreements

- Each milestone starts with a short written note of what will be built and ends with a
  demo against the goal above; anything that fails the demo is fixed before moving on.
- Defaults chosen by the builder (weights, thresholds, strike width, costs) live in the
  parameter model with a description each, so they are visible and easy to change in the
  app's config editor; `config/params.toml` seeds a new database with them.
- No real-order code path is ever added, even behind a flag.
