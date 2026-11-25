# TradeDisha — Development Plan

Requirements live in [intent.md](intent.md), with its companion
[enhancements.md](enhancements.md) for enhancements not yet merged into it. This plan is
the build history: the milestones the product was built in, in order. Milestones 0 to 6
made version 1.0.0; the E, C and S milestones followed as the enhancements came in. Every
milestone ends with something that runs and can be looked at, so the direction can be
corrected early rather than at the end.

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

- Backend: Python 3.12 managed with uv; FastAPI + uvicorn; pydantic and
  pydantic-settings for models and settings; `websockets`, `httpx` and `protobuf` for the
  broker (`grpcio-tools` in dev, to regenerate the protobuf code); SQLite through the
  standard `sqlite3` module; pure-Python indicator maths; pytest, pytest-asyncio,
  hypothesis; ruff, mypy strict, pre-commit.
- Frontend: Vite + React 19 + TypeScript (strict); Zustand for live stores; plain `fetch`
  for REST; TradingView `lightweight-charts`; Tailwind v4 with a design-token theme;
  ESLint, Prettier, Vitest with Testing Library and jsdom.
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
| E9 | One Market view panel | 2026-11-16 | built; checked in a browser |
| E10 | Headlines | 2026-11-17 | built, with unit tests |
| E11 | Sector indices, ATM in Details | 2026-11-17 | built, with unit tests |
| E12 | Macro evidence: dollar, crude, gold | 2026-11-18 | built; weights to be tuned on recorded weeks |
| E13 | Futures OI, order flow and the other metal in the bullion bias | 2026-11-18 | built; replayed on 16–18/11 |
| E14 | GIFT Nifty opening gap in the NIFTY bias | 2026-11-19 | built; checked against Upstox |
| E15 | Factor switches in the Evidence panel | 2026-11-19 | built; superseded the same day by E16 |
| E16 | Factor switches in the versioned config | 2026-11-19 | built; checked by the owner in the app |
| — | Config drawer (not a milestone) | 2026-11-19 | built, with unit tests; checked by the owner in the app |
| E19 | Executed paper trades page | 2026-11-25 | built; checked by the owner in the app |
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
`MarketDataProvider` interface and `AuthService` without touching the rest. *(Built in
Milestone 5, with the live Upstox feed; in daily use since.)*

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
which equals market open when the app starts before 09:15. *(Both resolved since: IV
comes from the feed and delta is computed when absent; opening OI is backfilled in
Milestone 6. See spec §17.)*

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
them pure. Late-start candle backfill belongs to the Upstox adapter. *(Built in Milestone
6.)*

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
and click-through from a journal row to the signal's evidence (it came with the Trades page,
Milestone E19).

**This completed version 1.0.0.**

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
- ~~Not done: the full-day 1x soak (memory, latency at 15:29, frame drops) has not been
  run. Backfill responses are parsed as documented by Upstox and are unverified live.~~
  Both since done: the soak was run by the owner (above), and backfill is in live use
  (spec §17).

---

## Enhancements

Built after release 1.0.0. Each request, with what was decided and the items left for
later, is documented in [enhancements.md](enhancements.md), the companion to
[intent.md](intent.md), and merged into intent.md from time to time.

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
  only; any failure leaves the tab out and the index feed untouched. *(Superseded by E6:
  bullion ticks are recorded in `bullion_ticks`, replayed with `TRADEDISHA_REPLAY_BULLION`,
  and drive bullion signals and paper trades. Failures still leave the index feed
  untouched.)*
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
  outages logged as `bullion_gap_start`/`bullion_gap_end`; display only. *(Since E6 it
  also gates bullion signals and paper trades.)*
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

## Milestone E9 — One Market view panel

**Goal:** the market view and the evidence that produces it in one full-width panel, with
the signal on its own row.

- "Market view" holds the bias meter (full width) with the evidence table and the
  order-flow line below it; the separate Evidence panel is gone.
- The signal is its own panel, above Market view by default; every panel now moves on its
  own (the market view + signal pair from E3 is retired).
- A layout stored in the browser is carried over: the old pair becomes Signal then Market
  view in its place, the old Evidence slot is dropped, and minimise states are kept.
- Applies to the index tabs and BULLION alike. On BULLION the metal cards' day, liquidity,
  contract and next-month figures go behind a Details toggle like the index tile's (closed
  by default, one remembered choice for both cards).
- Tests: the panel model (units, default order, carrying over an old order and old
  minimise flags, independent moves, restore); the panel summaries.

**Demo:** open the app fresh: Index, Signal, Market view (meter, then evidence and order
flow), Price chart, Open paper trades, Signals today. Move Signal and Market view
separately; restore. In a browser that had a moved layout, the pair's place is kept.

**Status (2026-11-16):** built, with unit tests, and checked in a browser on the
synthetic feed, including a pre-E9 stored layout carried over.

**Design:** spec §13.1, §13.2 (Panel order, PanelFrame).

## Milestone E10 — Headlines

**Goal:** a quick check on what is moving the market: Upstox headlines for the heaviest
NIFTY and BANK NIFTY stocks, newest first, under the option chain.

- Display only: no news reaches `engine/`, `indicators/` or the bias and signal path; no
  table, migration or REST endpoint. A news failure never touches the feed.
- Built in this order, one test cycle each:
  1. `config/news-stocks.txt` (30 `SYMBOL NSE_EQ|ISIN N|B|NB` lines, keys checked against the
     instrument file), `load_news_stocks` in `market/news.py`, the `news_stocks_file`
     setting, and the `news.poll_seconds` parameter (edited in the app, applied at once).
  2. `parse_news` (pure: merge by link then heading, symbols kept, newest first) and
     `fetch_news` in `feed/upstox.py` (all pages, 401 -> `Unauthorized`).
  3. `NewsService` and the `NewsChanged` event: poll every 180 s while the token is
     valid, wake on `AuthChanged("valid")`, statuses `needs_login` / `loading` / `ok` /
     `error`.
  4. Wiring: `AppState.news`, `build_state`, the lifespan; `HeadlineOut` / `NewsOut` in
     `schemas.py`, `news` in `hello`, the `news` frame from `WsHub`.
  5. Frontend data: `api/types.ts`, the store's `news` and `applyNews`, `api/ws.ts`.
  6. `components/Headlines`: day groups, rows, chips coloured by index, freshness colours,
     link, summary toggle, unseen bar, states, and the
     minimised summary.
  7. Panel state: `news` in `lib/panels.ts` (does not move), the hidden flag,
     `newsHeight` in `lib/layout.ts`, `PanelFrame.onClose`, the TopBar Headlines toggle.
  8. `components/RightColumn`: the chain / headlines rules of spec §13.1, wired into
     `App.tsx` in place of the chain's `SidePanel` block.
  9. Docs (spec, dd, CLAUDE.md frame list, README status), `make check`, demo.
- Tests: the stock file (comments, bad lines, more than 30, the shipped file valid);
  `parse_news` table cases, including items with no summary, no heading or a non-numeric
  time; `fetch_news` paging, 401 and 500; `NewsService` with a mock transport: no token
  -> no request, a change publishes once, the same list publishes nothing, 500 and
  timeouts keep the last list and recover, 401 marks the token expired, a bad stock file
  shows its error, a login wakes the poller; `hello` and the `news` frame; the Headlines
  component (order, times, chips, a `javascript:` link shown as text, states, new count);
  panel and layout parsing with old stored values; every RightColumn case.

**Demo:** with the live login, headlines appear under the chain within seconds, newest
first. Collapse them (the chain fills), hide them (the top bar's toggle brings them back),
minimise the chain (headlines fill), open BULLION (headlines alone), Restore panels. On the
synthetic feed the panel says it needs the Upstox login.

**Status (2026-11-17):** built, with unit tests (backend and frontend); `make check` green.
Not yet checked in a browser: the owner verifies it by hand.

**Design:** spec §3.1, §6.7, §12.2, §13.1 (Right column with headlines), §13.2 (Headlines,
SidePanel, PanelFrame, Resizable layout).

## Milestone E11 — Sector indices, ATM in Details

**Goal:** see how the sectors behind the index are moving, beside spot and futures.

- `sector_indices` setting: NIFTY shows Auto, FMCG, IT, Pharma, Metal, Energy, Realty,
  Media, Fin Service and PSU Bank; BANK NIFTY shows PSU Bank, Pvt Bank and Fin Service.
  Upstox `NSE_INDEX` keys, subscribed beside India VIX on every feed but the synthetic one
  (`market_wide_keys()`), each once.
- `IndexStats.sectors` (`sector_quotes()`): level, previous close, change and change %;
  sent with the index's stats (REST and the `stats` frame).
- The Index panel: spot and futures on top; a Sectors block of small boxes, one per
  sector: name (readable size and colour), value, and change with change %
  (`+464.00 (+1.24%)`), coloured; it collapses like Details (open by default, remembered),
  showing how many sectors are up and down while closed;
  ATM and the strike count move into Details as an Options group.
- Display only: no indicator, signal or paper trade reads sector data.
- Tests: sector keys, labels and quotes (missing prices empty); the subscription list
  (VIX first, each sector once, none on synthetic); the default lists; the stats API on
  the synthetic feed; the panel (ATM only in Details, sector boxes and colours, dashes,
  no block without sectors).

**Demo:** on the live feed the NIFTY tab lists ten sectors with level and change %, BANK
NIFTY its three bank sub-indices; Details opens on ATM and the strike count. On the
synthetic feed the sectors show "—".

**Status (2026-11-17):** built, with unit tests; `make check` green. Not yet checked in a
browser: the owner verifies it by hand.

**Design:** spec §3.1, §7.4, §13.1, §13.2 (IndexTiles).

## Milestone E12 — Macro evidence: dollar, crude, gold

**Goal:** the index and bullion biases take account of the dollar, the rupee, crude oil
and gold, live with a small weight.

- Upstox has no dollar index, so `dollar_index_proxy()` rebuilds it from NSE's USD/INR,
  EUR/INR, GBP/INR and JPY/INR futures (the euro, yen and pound: 83 % of the real DXY).
- `market/macro.py:MacroTracker`: the four currency futures and MCX CRUDEOIL (near month),
  with their own candle builder; gold and silver from the bullion tracker. Side-market
  keys (`MCX_FO|`, `NCD_FO|`) never reach the index candles or index liveness, and are
  recorded in `bullion_ticks`. Loaded live and in replay with `replay_bullion`; backfilled
  at start; fails soft.
- `indicators/macro.py`: each instrument's move over `macro.window_minutes` (30), scored
  `sign · clamp(move / full%)`. Index: dollar, USD/INR, crude and gold all bearish when
  rising; silver shown as `info`. Bullion: dollar bearish, USD/INR bullish.
- Aggregator: a fourth group, `macro`, with `weights.macro` (0.10) carved out and the
  others keeping their proportions, so every saved config stays valid; `bullion_weights()`
  with `bullion.macro_weight` (0.10). With no live macro price the share goes back and the
  bias is the pre-E12 one.
- Evidence table: a Macro group; `info` rows muted.
- Tests: the proxy maths and signs; moves, clamping and warming; align and forward fill;
  weights, the idle share and expiry day (with a property test); old configs loading; the
  currency parser and contract months; the tracker and the view; side-market routing;
  macro in the index and bullion bias breakdowns; the evidence table.

**Demo:** on the live feed Market view shows the Macro rows for NIFTY, BANK NIFTY and on
BULLION (dollar and USD/INR); after 17:00 the currency rows go to warming and the bias
carries on without them. On synthetic there is no macro data and the bias is as before.

**Status (2026-11-18):** built, with unit tests; `make check` green. Not yet checked on
the live feed: the owner verifies it by hand. The weights and full-strength moves are
starting values to be tuned with `tools/score.py` once macro ticks have been recorded for
some weeks.

**Design:** spec §3.2, §6.8, §8.4, §8.6, §9a; signal.md §3.4, §4, §13.

## Milestone E13 — Futures OI, order flow and the other metal in the bullion bias

**Goal:** the gold and silver bias reads more of what Upstox already sends for the near
future, not just its price.

- `indicators/futures.py`: `futures_oi` (price change against OI change over 15 minutes;
  build-up full, covering and unwinding half; warming across a feed gap), `net_volume`
  (signed volume share over 15 candles) and `book_imbalance` (the book's lean against its
  30-minute average). `indicators/macro.py:peer_metal`: the other metal's trend.
- `BullionTracker.minute_book()`: the near contract as it stood at the end of each minute
  (OI, total and five-level book quantities), kept 900 minutes.
- Aggregator: a `flow` group (0 for the index); `bullion_weights()` from the new
  `bullion.oi_weight` (0.15) and `bullion.flow_weight` (0.15), macro 0.10, trend the rest;
  the groups that give an idle share back are an argument (`BULLION_IDLE`).
- `CandleBuilder`: a volume jump after more than 30 s of silence is counted but not
  signed.
- Ten `bullion.*` parameters with help text, in the model and `config/params.toml`; old
  stored versions load with the defaults. Evidence table: an Order flow group and labels.
- Tests: the three indicators table-driven (classes, clamping, window, warming, the gap)
  with a property test for bounds; the peer; the idle share; the weights validator; the
  tracker's readings; a live-tick bias with every group live; the gap volume; old configs
  and the seed file; the evidence table.

**Demo:** on the live feed the BULLION Evidence panel shows Open interest, Order flow and
the other metal's trend under Macro; for the first 15 minutes after start they warm and
the bias is trend (and the dollar) alone. Replay a recorded day with
`TRADEDISHA_REPLAY_BULLION=true` to see the same.

**Status (2026-11-18):** built, with unit tests; `make check` green. Replayed offline on
the recorded MCX sessions of 16–18/11/2026 against the previous build: 168 bullion
signals before, 80 after; SILVER better (+0.04 % → +0.10 % per signal), GOLD worse
(+0.04 % → −0.02 %), with no costs and overlapping signals. Too little data to judge: the
weights and full-strength values are starting values to be tuned once some weeks are
recorded. Not yet checked on the live feed: the owner verifies it by hand.

**Design:** spec §7.1 (net volume), §8.4, §9a; signal.md §13.

## Milestone E14 — GIFT Nifty opening gap in the NIFTY bias

**Goal:** NIFTY's bias takes account of how far the market moved overnight, as GIFT Nifty
shows it, for the first minutes after the open.

- Upstox has GIFT Nifty only as a global index (`GLOBAL_INDEX|SGX NIFTY`, global
  instrument file), refreshed every 120 s, with candles on REST; there is no GIFT Bank
  Nifty. During NSE hours it repeats the NIFTY future, so only the overnight move is used.
- `indicators/gift.py`: `snapshot_from()` takes GIFT's last close before the previous NSE
  close and before today's open; `gift_gap()` scores the move
  `dir · clamp(move / gift_full_pct) · (1 − m / gift_fade_minutes)`, `info` once faded,
  `warming` without a reading. In the macro group, NIFTY only.
- `market/gift.py:GiftNifty`: live, a minute after the open, fetches the previous NSE
  day's and today's 1-minute candles (`fetch_day_candles`, new), retrying every 2 minutes;
  stores the reading in `gift_nifty` (migration 013, `store/gift.py`). Replay reads the row;
  `tools/score.py` copies it. Fails soft.
- `BiasEngine`'s macro hook takes the index as well as the minute.
- Three `macro.gift_*` parameters with help text, in the model and `config/params.toml`.
  Evidence table: a `GIFT Nifty gap` label.
- Tests: the snapshot (cut-offs, a missing minute, missing prices) and the vote (follow,
  fade, the fade-out, clamping, warming) table-driven with a property test for bounds; the
  store; the fetch (previous trading day over a weekend and a holiday, nothing stored
  without a price, when it is due); NIFTY gets the vote and BANK NIFTY does not; the
  scorer copying the row; the evidence table.

**Demo:** on the live feed, from the 09:16 minute close NIFTY's Evidence shows `GIFT Nifty
gap` under Macro with the overnight move and the weight left, fading to "not scored" by
09:45; BANK NIFTY has no such row. The log shows `GIFT Nifty a -> b (±x%) overnight`.

**Status (2026-11-19):** built, with unit tests; `make check` green. Checked against
Upstox on 19/11/2026: GIFT 25 237.5 at 15:29 on 18/11, 25 154.0 at 09:14, −0.33 %.
Replayed with `tools/score.py` on 16–18/11/2026 with the real GIFT readings (+0.23 %,
−0.17 %, −0.49 %) against no readings: the same 37 `minute_close` and 64 `trigger`
signals, with the same outcomes. The vote was live (18/11: −0.91 at 09:16, fading to
`info` at 09:44) but, as the only macro reading in a replay without `replay_bullion`, it
moved NIFTY's bias by at most 0.09 against a 0.50 entry threshold; live, sharing the macro
group with up to four other readings, it moves it by at most about 0.02. Giving it real
influence needs a weight of its own, which the owner decides. Not yet checked on the live
feed: the owner verifies it by hand.

**Design:** spec §6.8, §8.6; signal.md §3.4.

## Milestone E15 — Factor switches in the Evidence panel

**Goal:** the trader can leave any factor out of an index's or metal's bias with a switch
on its Evidence row; every factor is on by default.

- `engine/aggregator.py:aggregate(off=...)`: a factor switched off is shown with weight
  and contribution 0 and left out of its group's score; a group with every member off
  hands its share back. `Contribution.enabled`, stored in every breakdown.
- `engine/factors.py:FactorSwitches`: per index or metal, in `app_state.factors_off`;
  announces `FactorsChanged`. Not a config version (the owner's choice). Both bias engines
  read it at each evaluation.
- API: `GET /api/factors`, `PUT /api/factors/{scope}/{name}`, `DELETE /api/factors/{scope}`;
  `factors` in `hello` and a `factors` frame. `IndicatorOut.enabled` (true for old rows).
- Evidence table: a switch per row (waits for the server), "(off)" rows dimmed, "off/on
  from the next minute close" until the bias catches up, "Turn all back on".
- Tests: the aggregator (the share moving inside a group and between groups, factors
  carrying no weight, unknown names) with a property test; the service (per scope,
  restart, events, a corrupt value); the API (scope and name checks); the socket; a bias
  engine breakdown; old breakdowns; the table's switches, pending and off states, errors.

**Demo:** on the synthetic feed switch off Put-call ratio on NIFTY: the row says "off from
the next minute close", then shows "(off)" with weight 0 while ATM OI build-up carries
Open interest's whole share; BANK NIFTY is unchanged; "Turn all back on" restores it.

**Status (2026-11-19):** built, with unit tests; `make check` green; the demo above checked
in a browser on the synthetic feed. Superseded the same day by E16: the switches moved into
the config, and the Evidence panel shows them read only.

**Design:** spec §8.4; signal.md §4, §11.

## Milestone E16 — Factor switches in the versioned config

**Goal:** the factor switches are parameters, so each signal's config version says which
factors were on; they are flipped in the Config control and shown read only in Evidence.

- `parameters/model.py`: `factors` with `nifty` (`NiftyFactors`, 15), `banknifty`
  (`IndexFactors`, 14), `gold` and `silver` (`BullionFactors`, 9), each `"on"`/`"off"`,
  default on; `off_for(scope)`. Old versions load all on. Seeded in `config/params.toml`.
- `ParameterService.set_factor` and `PUT /api/parameters/factors/{scope}/{name}`: one flip,
  one version tagged `Factor NIFTY.pcr: off` (none when already so; 422 for an unknown
  factor); the usual `parameters` frame. `describe()` skips `factors`; a typed save keeps
  the switches in force.
- Engines read `p.factors.off_for(...)`. E15's store, routes, event and frame removed;
  migration 014 deletes `app_state.factors_off`, so every factor starts on.
- Config control: a **Factors** tab (its label counts the factors off), one list per index
  and metal, a working switch per factor that saves at once. A tab rather than a section of
  the Edit form, because each flip is a new version and the form restarted on a new version.
  *(Since the Config drawer below, the form keeps unsaved edits across a new version; the
  Factors tab stays a tab of its own.)*
- Evidence panel: a read-only switch per row from the config in force, "(off)" rows
  dimmed, "off/on from the next minute close" until the bias catches up, and "N factors
  switched off. Change in Config, Factors."
- Tests: the model (defaults, old versions, scope mapping, bad values), a name-drift test
  against both pipelines, `set_factor` (fixed tag, no-op, unknown factor, typed save keeps
  switches), the API and its frame, the next bias, migration 014; the Factors tab, the
  read-only Evidence switches.

**Demo:** in Config → Factors switch NIFTY's Put-call ratio off: version `Factor
NIFTY.pcr: off` appears; at the next minute close NIFTY's Evidence row shows a read-only
off switch, "(off)" and weight 0; BANK NIFTY is unchanged. Offline, a trial file with
`[factors.nifty] pcr = "off"` given to `tools/score.py` replays with it off.

**Status (2026-11-19):** built, with unit tests; `make check` green. Offline replay of
18/11/2026 with such a trial file: all 1,356 NIFTY minutes had `pcr` off (weight 0),
BANK NIFTY's on. Checked by the owner in the app the same day; the Evidence panel's
read-only state is a flat label (a green ON, a grey OFF), unlike the Config tab's switch.

**Design:** spec §8.4; signal.md §4, §11.

## Milestone E17 — Paper bank account

**Goal:** paper trades are funded by a fake bank account. A trade opens only if the bank
can block its money, and its net P&L is deposited or deducted when it closes. The opening
balance is a parameter.

- `parameters/model.py`: `bank.opening_balance` (₹25 lakh), plus `bullion.gold_margin_pct`
  (10) and `bullion.silver_margin_pct` (12); seeded in `config/params.toml`, edited in
  Config → Parameters.
- `engine/bank.py:PaperBank`: one per `FeedSession` (shared by the index and bullion
  managers, there before the feed starts). A changed opening balance is recorded in
  `bank_ledger` as a deposit or withdrawal of the difference (the first read records the
  opening deposit); `summary()` derives balance, blocked and available from the funded
  trades; `reserve()` refuses a trade it cannot fund.
- `engine/paper.py`: `PaperRules.block`: an option's premium × qty + cost, a future's
  margin % of value + cost. `PaperTrade.blocked` and `.banked`. A refused open leaves the
  signal active.
- Migration 015: `bank_ledger`, plus `paper_trades.blocked` and `.banked`.
- `GET /api/bank`; `bank` in `hello`; a `bank` frame after each trade change and each
  parameters change.
- Page: a Paper bank strip (balance, blocked, available, unrealised, P&L since the bank
  opened) above the open trades and at the top of the journal, available in red at or
  below zero; the journal also lists the cash ledger; a Blocked column on open trades. A refused open shows on the signal card as
  "Not opened: not enough money in the paper bank…".
- Tests: block amounts per market, refusal (and the signal staying active), settlement on
  manual, target and stop exits, a deposit and a withdrawal on edit (P&L kept), revert and
  same-amount save, a withdrawal beyond the free money, pre-bank trades, a futures loss
  beyond margin, the shared account, a hypothesis property test of
  the books, the API, `hello` and the frame; the strip and the store.

**Demo:** the strip shows Available ₹25,00,000. Open a NIFTY option trade: Blocked rises
by premium × qty + cost; close it and Blocked returns to zero while Balance moves by the
net. Set the opening balance to ₹10,000 in Config: a withdrawal of ₹24,90,000 is recorded,
the balance falls by that much, and the next trade is refused on its card. Set it back:
a deposit, and the same signal can be traded.

**Status (2026-11-20):** built, with unit tests; `make check` green. Checked end to end on
the synthetic feed the same day (open, close, a refused open, the signal still tradable).
Then changed with the owner: a change of the opening balance was first a fresh account
(earlier P&L stopped counting); it is now a deposit or withdrawal of the difference.
Checked end to end again: a +₹7.50 trade, then ₹25 lakh → ₹10,000 withdrew ₹24,90,000
(balance ₹10,007.50, the next trade refused), then back to ₹25 lakh deposited it (balance
₹25,00,007.50, the same signal traded); the journal lists the three cash moves, and the
bank was unchanged across a restart.

**Design:** spec §10.5.

## Milestone E18 — Pause bullion around US data releases

**Goal:** no GOLD or SILVER signal fires in a window around a US data release (CPI,
payrolls), where a 1-minute trend signal is mostly noise. The releases are a hand-kept
file; the window and what else it stops are parameters.

- `config/us-events.txt`: `YYYY-MM-DD HH:MM label` per line, IST, read at start
  (`us_events_file` setting). Ships with the format and no events.
- `market/us_events.py`: `load_us_events()` (sorted; a bad line raises with its line
  number) and `event_in_window()`. `FeedSession.us_events` loads it soft: a bad file is
  logged and bullion runs without a pause.
- `parameters/model.py`: `bullion.event_pause_before_minutes` (15),
  `event_pause_after_minutes` (15), `event_end_waiting` (off), `event_block_trades`
  (off); seeded in `config/params.toml`.
- `engine/bullion_signals.py`: gate `event_pause` after `outside_hours`, before
  `feed_down`; with `event_end_waiting` on, a waiting signal lapses when the window opens
  (evaluation or housekeeping). `trade_block()` gives the refusal reason.
- `engine/paper.py`: `PaperRules.entry_block`; `bullion_rules(entry_block=...)` refuses an
  open with "paused around US data: CPI 19:00" when `event_block_trades` is on.
- Page: the signal card's reason "paused around a US data release".
- Tests: file parsing and the window bounds as a table; gate placement and order; the
  waiting signal kept or lapsed by the switch; a manual open allowed or refused by the
  switch; an open trade still reaching its target in the window; a stored version without
  the new fields; the session reading the file, and a bad file leaving bullion running.

**Demo:** add a line for a release a few minutes ahead and restart. From 15 minutes
before it the GOLD and SILVER cards read "paused around a US data release" while the bias
still updates. Turn on `event_block_trades`: Paper trade on a waiting signal is refused
with the release named. After the window, signals fire again.

**Status (2026-11-24):** built, with unit tests; `make check` green apart from an
existing flaky websocket test (`tests/test_net_volume.py`, about 1 run in 5 on `main`
too). Not yet checked end to end with the owner.

**Design:** spec §9a; signal.md §13.6, §13.8–13.10.

## Milestone E19 — Executed paper trades page

**Goal:** a page of the paper trades that have been closed, where each one opens to why it
was taken and how it went: levels and fills, P&L, the signal, what the instrument did after
it, and the evidence at the minute it fired. Display only; nothing new is stored.

- `api/paper.py`: `GET /api/paper-trades/{id}` → `PaperTradeDetailOut {trade, signal}`.
  An open trade comes from its manager (live P&L), a closed one from `paper_trades`; the
  signal from `signals` (index and bullion share it), so it works before the feed starts.
  404 for an unknown id.
- `api/signals.py:signal_out`: with no outcome tracker (feed not started) the outcome is
  read from `signal_outcomes`, so `GET /signals/{id}` gains it too.
- Page: `lib/view.ts` (pages and their hash); the TopBar's single Journal toggle becomes
  Dashboard · Journal · Trades. `components/TradeLog/` lists closed trades by IST day (count,
  won/lost, net) with Market, From and To filters; a trade's row opens its detail, fetched
  once and kept. `lib/signalBias.ts:biasFromSignal()` turns a signal's stored breakdown back
  into a `BiasOut` for `EvidenceTable`. The exit-reason and fill-quality labels move to
  `lib/tradeText.ts`, shared with the Journal.
- Journal: its trade table and the Exit and Fill filters that narrowed it are removed (the
  owner's follow-up: no trade listed twice). It keeps the bank, the ledger and the summary
  cards, loads only `/journal/stats`, and links to the Trades page, which takes the Exit
  and Fill filters.
- Open trades too (the owner's second follow-up): the page loads every status; open trades
  head it under "Open now" with their unrealised total. `TradeLog` takes the store's trades
  (`latest`) and `now`, so an open trade's price, net and time held tick from the socket and
  a close moves the row before the refetch; its detail reads "Now", "Net so far" and
  "Result so far in R". The Exit and Fill filters hide open trades.
- Close from the page (the third follow-up): each open row has a Close button calling
  `closePaperTrade`; App's `closeBlock` disables it with the reason while that trade's
  market (index feed, or MCX for a metal) has no live price; a refusal shows "Not closed:".
- Tests: the endpoint for an open, a closed, an unknown and a bullion trade, and the outcome
  read without the tracker; the page's filters, day grouping and totals, detail facts
  (slippage, risk : reward for a bought option and a short future, result in R, signal,
  outcome, evidence), the detail cache, a failed detail and its retry, a missing signal,
  the Exit and Fill filters; open trades first with live P&L, a socket update and a close
  without a refetch, the filters hiding them, an open trade's detail; closing from a row,
  a refused close, a market with no live price; the Journal with no trade table and a link
  to the page; the hash mapping; the TopBar buttons.

**Demo:** paper-trade a signal and close it from Open paper trades. Trades in the TopBar
lists it under today with the day's net; open it: the fill against the signal price, target
and stop, risk : reward, net and R, the signal's bias, rule and config version (hover for
the values), what the option did after, and the evidence table as it was then.

**Status (2026-11-25):** built, with unit tests; `make check` green; checked by the owner
in the app.

**Design:** spec §13.2 (Trades page), §12 (API).

## Frontend review fixes (26/11/2026, not a milestone)

**Goal:** the owner asked for a review of the frontend and its five most important
issues, fixed. Each fix started with a test that failed on the old code.

- **Market time on the page** (`lib/marketClock.ts`): every time shown was measured with
  the browser's wall clock against market timestamps, so in replay the signal countdown
  sat at 0:00, the feed's age read hundreds of hours and the top bar showed today's time.
  Every frame now carries `t_mkt` (the market clock when sent; `api/ws.py`); the page
  re-bases on it and `useMarketNow` drives the top bar, the signal, open trades and the
  Trades page. The "applies from" minute is the market clock's next minute on both sides
  (`api/analysis.py`).
- **Config-version tooltip** (`ConfigVersionChip.tsx`): a chip reused for another signal
  (tab switch) kept showing the first version's values. The loaded detail is now keyed
  by version, and a late reply for an old one is dropped.
- **Busy per row** (`lib/useInFlight.ts`): one busy id covered every row, so closing a
  second trade re-enabled the first mid-request (a second click gave a false "Not
  closed"), and the signal card's "Opening…" followed it across tabs. Requests in flight
  and refusals are now kept per trade or signal (open trades, the Trades page, the card).
- **"Applies from" after a save** (`ConfigControl.tsx`): a local copy of the save's
  minute was never cleared and hid later changes from another tab. The store's minute is
  shown.
- **Stuck price flash** (`lib/useFlash.ts`): a value going blank mid-flash left it lit.

**Status (2026-11-26):** built, with tests; `make check` green.

**Design:** spec §12.2.

## Review fixes (26/11/2026, not a milestone)

**Goal:** the owner asked for a code review and its five most important issues, fixed.
Each fix started with a test that failed on the old code.

- **Routes on the loop** (`api/*.py`): the routes were plain `def`, so FastAPI ran them
  in worker threads beside the event loop. Two clicks on one signal opened two trades
  (45 runs in 50), a manual close could race a target hit, and a latency post could change
  a deque while the loop read it, killing `_housekeeping` for good (no square-off, lapses
  or gap tracking). Every route is `async def` now except `/data/usage` and `/auth/login`.
  Each housekeeping step is guarded on its own (`_chore`).
- **Chain before candles** (`market/session.py`): the spot candle closed, and the bias ran,
  before the chain closed its minute on the same tick. When the spot tick opened a minute,
  the OI and premium votes read the previous minute's chain. The candle step is now a tick
  consumer subscribed after the chain manager.
- **Candles after the wall-clock flush** (`market/candles.py`): a late tick reopened a
  flushed minute (a second candle replaced the real row and the bias ran twice), and live
  made no carry-forward candles after an outage, unlike replay. The builder now judges a
  tick against the last closed candle: older ones are dropped, and gaps are filled within
  one IST day, never from backfilled candles.
- **Logout during a reconnect** (`feed/upstox.py`): a handshake already in flight
  installed its socket after the logout, so ticks kept flowing. `drop()` is counted, and
  a socket opened across one is closed.
- **Gate reasons a minute behind** (`api/ws.py`): the hub hears the bias before the
  signal engines do, so `bias` and `signal` frames carried the previous minute's gates.
  The gates are now read when the frame is sent.

**Measured:** replaying 23/11/2026 with `tools/score.py` gives the same scorecard to within
one signal (the trigger rule 21 → 22 signals, BANK NIFTY). These fixes are about data
integrity, not the strategy.

**Status (2026-11-26):** built, with tests; `make check` green.

**Design:** spec §7.1, §12.1.

## Performance pass (25/11/2026, not a milestone)

**Goal:** the owner asked for a performance review with changes that keep behaviour and
look as they are. Measured on the running app first: the backend had headroom (3–4% CPU,
ingest to send p99 16 ms in market hours); the cost was in the browser, plus two bugs.

- Latency (`lib/latency.ts`): one animation-frame callback per paint for every frame
  received since the last one, none while the tab is hidden. Before, each tick frame
  queued its own callback; a hidden tab piled them up (about 144,000 an hour) and its
  `recv_to_paint` read minutes (p50 60 s, worst 50 min on 16/11).
- SQLite (`store/db.py`): `auto_vacuum = INCREMENTAL` before `journal_mode = WAL`; the
  other order left every file at 0, so pruning never shrank one (live.sqlite: 1.05 GB of
  1.55 GB free pages). `tools/compact.py` (`make compact`, app stopped; refuses while the
  port answers) rewrites an old file once with `VACUUM`. `recorded_days()` reads MIN and
  MAX as two subqueries (84 ms → 0.07 ms on 2.9 M rows).
- Rendering: `App` no longer reads the slices that change with the frames;
  `components/Live/` panels read them (tiles, bullion cards, signal, market view and flow
  line, open trades, history, chain, headlines, the top bar's clock and feed age, the
  Journal's bank, the Trades page). `App` selects small values instead (metal names,
  trade revision, the active signal's id, the open trades' ids; `lib/marketViews.ts`).
  `useNow` is one shared timer per interval. Headline and Trades-page rows are memoised
  and given what they show (freshness band; `now` only for open trades).
- Tests: the sampler (one callback, hidden tab, dropped on hide), the shared clock, the
  market views, `App` not re-rendering for ticks, chains or flow (fails on the old `App`),
  rows skipping the clock (fail on the old components), a new file's vacuum mode, a prune
  shrinking the file, the compact command and its refusal.

**Measured** (production builds of before and after, alternating, same live backend):
components rendered per commit 135 → about 36; script time in quiet minutes 11.7 → 4.1
ms/s. Layout, text and element positions identical on the dashboard, BULLION, Journal
and Trades pages; no console errors.

**Status (2026-11-25):** built, with unit tests; `make check` green. `make compact` not
yet run on live.sqlite (needs the app stopped).

**Design:** spec §10.4, §11, §14a.

## Top bar redesign (25/11/2026, not a milestone)

**Goal:** the owner found the top bar scrolling sideways (Logout hidden off the edge at
1440 px), the items after the feed's tick age jumping as the number changed width, and
every control looking the same.

- Groups, left to right: the brand, a link home (`/`, the dashboard; a plain click
  switches page in place, a modified click opens a new tab); a borderless status strip
  (market and clock, feed, login, replay day); then on the right, each after a rule, the
  pages as a tab strip (Dashboard · Journal · Trades, the open-trade count now on Trades,
  where open trades are listed), the dashboard's view tools (Restore panels, Headlines),
  the app's tools (Data, Config, Latency, theme) and Login (filled) or Logout (outlined,
  red on hover). Tools are borderless
  with an icon (`components/Icons/`, `lib/toolbar.ts:toolClass`), lit when on; the page
  tabs have icons too, and the open-trade count is a small bubble on Trades (the words in
  its tooltip). One line at 1280 px; "Restore panels", when shown, may wrap it there.
- Headlines opens and closes the headlines panel: lit while it is on the page and
  expanded (`usePanels().newsShown`); a click takes it off, or brings it back expanded
  whether it was hidden or minimised (`showNews`). The headlines no longer count towards
  "Restore panels" (`changed`), and Restore leaves them alone, so turning them off adds no
  second button.
- The feed's tick age is a fixed five characters wide in even-width digits
  (`fmtTickAge`: 400ms, 12.3s, 14m, 3h), so nothing after it moves. The feed reads "Feed"
  when connected (the dot's colour says so) and spells out any other state; provider and
  instrument count are in its tooltip.
- The Config button shows `v10` only; the tag, which can be long, is in its tooltip and
  the drawer.
- The bar wraps onto a second line instead of scrolling.
- Tests: the fixed-width age across a change, the age formatter's bounds, a non-connected
  feed spelled out, Logout last, the badge on Trades, the Config tag in the tooltip, the
  brand going home and the tabs placed after the status strip; Headlines from shown,
  hidden, minimised, and Restore leaving them.

**Status (2026-11-25):** built, with unit tests; `make check` green; checked by screenshot
at 1440, 1280 and 1024 px, dark and light.

**Design:** spec §13.1, §13.2.

## Logout (24/11/2026, not a milestone)

**Goal:** end the Upstox login on demand instead of waiting for the 03:30 expiry, and log
in again without restarting the app.

- `POST /api/auth/logout`: revokes the token at Upstox (best effort), deletes it from
  `sessions`, publishes `AuthChanged("missing")` and closes the feed socket. The rest of
  the session stays wired; the feed is down (degraded mode) until the next login, which
  reconnects within about a second (no backoff while waiting for a token).
- Top bar: the rightmost control is **Login** before login and **Logout** after; the
  "Login: …" status stays beside the feed pill. Logout's first click asks "Confirm logout?" (lapses
  after 4 s), the second logs out and waits for the server.
- Tests: revoke call and local logout, local logout when Upstox fails or is unreachable,
  no call without a token; provider drop → wait → reconnect and re-subscribe; the endpoint
  (400 on synthetic); the top-bar confirm, busy and error states.

**Status (2026-11-24):** built, with unit tests; `make check` green.

**Design:** spec §4, §12.

## Config drawer (19/11/2026, not a milestone)

**Goal:** the config is easier to read and edit: more room than a dropdown, and every
value explained where it is shown.

- The Config button opens a **drawer on the right** over a dimmed backdrop instead of a
  dropdown panel. It closes from its header line, a clear ✕ Close button, the backdrop or
  Escape.
- Three tabs: **Parameters** (was Edit), **Factors · N off**, **Versions** (was History),
  opening on Parameters.
- Parameters: each value's help text on the line below its name, then "Allowed: …" with
  its limits; groups headed in bold. Values not touched follow a new version when one
  arrives (a factor flip, a save, a revert); unsaved edits are kept (`rebase` in
  `ConfigControl.tsx`).
- Factors: each row has the toggle, the factor's name and a one-line plain explanation
  below it (`FACTOR_HELP` in `lib/factors.ts`).
- Versions: unchanged apart from an "in force" badge.
- Tests: the drawer and each way to close it, help and limits shown without hovering, the
  factor explanations, unsaved edits surviving a new version.

**Status (2026-11-19):** built, with unit tests; `make check` green; checked by the owner
in the app. Commit a891615.

**Design:** spec §13.2 (Config control).

## Milestone C1 — Editable, versioned config

**Goal:** the trader tunes the parameters in the app, can always get back to an earlier
set, and can see which set produced each signal.

- **Versions in the database.** Table `config_versions` (migration 010); the highest
  version is in force; a new database takes version 1 from `config/params.toml`.
- **Edit** (since 19/11/2026 the Parameters tab of the Config drawer). A form in the
  Config control built from a field list the server describes
  (kind, limits, help). A save needs a tag and a change, is validated as a whole, and
  applies from the next minute close.
- **History and revert** (now the Versions tab). Every version listed; reverting saves the
  old values as a new version.
- **Signals carry the version** (`signals.config_version`), shown as a chip on the signal
  card and in "Signals today"; hovering it shows that version's values, with those that
  differ from the config in force highlighted.
- "Reload config" and `POST /parameters/reload` are removed.
- Tests: the service (seed, save, tag and no-change refusals, revert, a stored version
  the model no longer accepts, surviving a restart); the field list; the stamp on live
  signals; the six routes and the websocket frame; the editor (save, server errors,
  discard, new version resets the form; since the Config drawer a new version keeps
  unsaved edits instead), history and revert; the chip and its panel.

**Demo:** change the entry threshold and save with a tag; see the version in the top bar
and in History (now Versions); try an invalid value and see it refused; wait for a signal and hover its
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
database grows (spec §17); the demo in a browser on a replayed day. *(Since done: the
order-flow fields are recorded live and the app is in daily use; table growth is watched
from the Data panel. See spec §17.)*

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
the mechanism, not that the rule is any good. Not yet done: a live day. *(Since done: the
shadow rule has run on the live sessions of 16–18/11/2026; see E14's status. S3 still
waits for five sessions of shadow data.)*

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
