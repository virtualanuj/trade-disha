# TradeDisha — Development Plan

Requirements live in [intent.md](intent.md), with its companion
[enhancements.md](enhancements.md) for enhancements not yet merged into it. This plan is
the build history: the milestones the product was built in, in the order they were built.
Milestones 0 to 6 made version 1.0.0; the E, C and S milestones, and a few passes that
were not milestones, followed as the enhancements came in. Every milestone ends with
something that runs and can be looked at, so the direction can be corrected early rather
than at the end.

Everything built before Milestone E20 is kept short here: its goal, what was built and how
it stands. The full notes as they were written, with each milestone's file-by-file list,
tests and demo, are in git: `git show b5d2d13:docs/plan.md`.

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

In the order they were built; the sections below follow the same order.

| Milestone | What | Built | Status |
|---|---|---|---|
| 0 | Skeleton that runs | 2026-11-12 | built |
| 1 | Live feed on screen, and recorded | 2026-11-12 | built on the synthetic feed; the Upstox parts came with 5 |
| 2 | Option chain panel | 2026-11-12 | built |
| 3 | Candles, chart, and market view | 2026-11-12 | built |
| 4 | Signals | 2026-11-12 | built |
| 5 | Paper trading and journal, and the live Upstox feed | 2026-11-13 | built; version 1.0.0 |
| 6 | Hardening for daily use | 2026-11-13 | built; demo and full-day soak run by the owner |
| E1 | Layout, dates and index details | 2026-11-13 | built; checked on the live feed |
| E2 | Minimisable panels | 2026-11-13 | built; checked on the live feed |
| S1 | Signal yardstick and order-flow recording | 2026-11-13 | built; order-flow fields recorded live |
| S2 | Order-flow trigger, in shadow | 2026-11-14 | built; shadow data being collected |
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
| — | Config drawer (not a milestone) | 2026-11-19 | built; checked by the owner in the app |
| E17 | Paper bank account | 2026-11-20 | built; checked end to end on the synthetic feed |
| E18 | Pause bullion around US data releases | 2026-11-24 | built, with unit tests |
| — | Logout (not a milestone) | 2026-11-24 | built, with unit tests |
| E19 | Executed paper trades page | 2026-11-25 | built; checked by the owner in the app |
| — | Top bar redesign (not a milestone) | 2026-11-25 | built; checked by screenshot |
| — | Performance pass (not a milestone) | 2026-11-25 | built; `make compact` not yet run on the live database |
| — | Review fixes (not a milestone) | 2026-11-26 | built, with tests |
| — | Frontend review fixes (not a milestone) | 2026-11-26 | built, with tests |
| E20 | Paper trades opened by hand, whole-rupee levels | 2026-11-26 | built, with unit tests |
| E21 | Gold BeES and Silver BeES | 2026-11-26 | built; accepted without an end-to-end check |
| E22 | Rates strip under the top bar | 2026-11-26 | built; accepted without an end-to-end check |
| E23 | Hover previews on Trades, Data and Latency | 2026-11-27 | built; accepted without an end-to-end check |
| E24 | GOLDM and SILVERM, and lots per contract | 2026-11-27 | built; accepted without an end-to-end check |
| E25 | Tabs by exchange: NSE and MCX | 2026-11-27 | built; accepted without an end-to-end check |
| S3 | Switch the trigger on, on evidence | — | planned: after five live sessions of shadow data |

---

## Milestone 0 — Skeleton that runs

**Goal:** a repository that starts, with both halves talking to each other.

**Built:** the uv backend with a FastAPI health endpoint; the Vite frontend with dark and
light theme tokens and the app shell; `.env.example`, the README and the `docs/` folder;
the gates (ruff, mypy strict, pre-commit, ESLint, Prettier, Vitest) behind one `check`.

**Status:** built.

## Milestone 1 — Live feed on screen, and recorded

**Goal:** real NIFTY and BANK NIFTY ticks flowing from Upstox into the browser, and saved
to disk for replay.

**Built:** the provider interface with synthetic and replay feeds; instrument resolution
(spot, near future, nearest expiry, the strike window); tick recording to SQLite and the
replay provider reading it back; WebSocket push; latency stamps on every tick and the
overlay; the top bar with market status, feed health and tick age.

**Status (2026-11-12):** built and demoed on the synthetic provider. The Upstox parts (the
login, the real instrument master, the websocket adapter) came with Milestone 5, behind the
same interfaces.

## Milestone 2 — Option chain panel

**Goal:** the right-hand panel of the final screen, live.

**Built:** chain state per index from ticks and the option-chain snapshot; ATM, PCR, OI
change since open and since the previous minute, max pain and build-up classes;
`chain_minutes` once a minute; re-centring with live subscribe and unsubscribe; the chain
table with ATM highlighted and OI heat; `/api/chain/{index}` and the `chain` frame.

**Status (2026-11-12):** built on the synthetic provider. Both open questions were settled
later on the live feed: IV comes from the feed and delta is computed when absent; opening
OI is backfilled (Milestone 6).

## Milestone 3 — Candles, chart, and market view

**Goal:** the main area shows the index chart and a live bullish/bearish meter with its
evidence.

**Built:** the 1-minute candle builder with gap fill; `candles_1m` and `bias_minutes`;
nine indicators as pure functions with unit and property tests; the weighted aggregator
with expiry-day reweighting; `config/params.toml` with validation (the reload button was
replaced by C1); the chart with overlays, the bias meter and the evidence table.

**Status (2026-11-12):** built on the synthetic provider. By design the bias is worked out
at every minute close whatever the market status (signals are what the hours gate), and
indicators recompute over the stored window rather than incrementally.

## Milestone 4 — Signals

**Goal:** the app issues recommendations with entry, target, stop, and reasons.

**Built:** the signal engine (fire, lapse, reverse, traded; open trades never gate; the
re-arm knob, off by default; hours and feed-live gates); expiry-day point targets through
the feed's delta or Black-Scholes; the `signals` table; REST and WS frames; a gate reason
per index; the signal card with countdown, chart markers and the day's history.

**Status (2026-11-12):** built on the synthetic provider.

## Milestone 5 — Paper trading and journal

**Goal:** one-click paper trades tracked to exit, with a journal that answers "is this
worth real money?"

**Built:** `PaperTradeManager`, opening only from the Paper trade button at the current
price and closing on target, stop, square-off or by hand, with fill quality (`live`,
`after_gap`, `stale`); net P&L with a per-trade cost; trades left open across a restart
picked up again; open trades on the dashboard with live P&L and the bias-reversed flag;
the Journal with summary cards. The live Upstox feed (login, instrument master, websocket)
came in the same milestone.

**Status (2026-11-13):** built; this completed version 1.0.0. The click-through from a
trade to its signal's evidence came later, with the Trades page (E19).

## Milestone 6 — Hardening for daily use

**Goal:** the app survives a real trading week without babysitting.

**Built:** one `banner` in `/api/health` for every degraded state, shown under the top bar
with last-known data dimmed; the late start (today's candles seeded, opening OI from the
chain snapshot, each part failing on its own); feed gaps detected, logged to
`feed_events` and marking open trades `after_gap`; fault injection on replay
(`TRADEDISHA_REPLAY_DROP`); tick pruning with the Data panel; `make start`, the backend
serving the built page.

**Status (2026-11-13):** built. The demo and the full-day soak were run by the owner, and
the backfill is in daily use.

---

## Enhancements

Built after release 1.0.0. Each request, with what was decided and the items left for
later, is documented in [enhancements.md](enhancements.md), the companion to
[intent.md](intent.md), and merged into intent.md from time to time.

## Milestone E1 — Layout, dates and index details

**Goal:** the screen fits how the trader works: panels sized to taste, dates in the
familiar format, and the day's key index facts one click away.

**Built:** dates as DD/MM/YYYY everywhere (`fmtDate`); dragged dividers for the chain
width and chart height, remembered and clamped; a hideable option-chain column; India VIX
and the 52-week range per index; the index details view. Previous close is stored with
recorded ticks, so a replay shows change on the day. Design: spec §6.2, §6.5, §7.4, §12,
§13.2–13.4.

**Status (2026-11-13):** built, and checked by the owner on the live feed, including the
52-week figures against NSE's and India VIX ticking.

## Milestone E2 — Minimisable panels

**Goal:** the trader can tuck any panel away so the others get the room, and bring it back
where it was, without missing a signal or an open trade.

**Built:** one `PanelFrame` around every panel, minimising to its title bar with a
one-line summary; a minimised signal or open-trades panel opens itself for a new signal or
trade; "Restore panels" in the top bar; the open paper trades panel always on the page.
Design: spec §13.2 (PanelFrame, SidePanel).

**Status (2026-11-13):** built, with unit tests; checked in a browser, and on a live day
by the owner.

## Milestone S1 — Signal yardstick and order-flow recording

**Goal:** know how good the signals are, and start recording what the trigger will need,
without changing a single signal.

**Built:** the order-flow fields of the `full` feed recorded with every tick; every signal
followed to target, stop or neither, with best and worst move and lateness (§9.5); the
scorecard (`GET /api/signals/scorecard`, the outcome column, a day line) and
`tools/score.py` to replay recorded days. Design: spec §6.2, §9.5, §11, §12.1, §13.2.

**Status (2026-11-13):** built. The order-flow fields are recorded live, and table growth
is watched from the Data panel (spec §17).

## Milestone S2 — Order-flow trigger, in shadow

**Goal:** see, on real days and without risk, whether "setup, then trigger" beats the
minute-close rule.

**Built:** a flow score per index from the future's book and trades and the ATM call and
put; the trigger rule (a setup from the last minute's bias, then order flow agreeing,
inside the minute); a shadow engine running whichever rule is not live, its signals scored
the same way, greyed on the page and never tradable; the scorecard split by rule and the
flow line under the evidence. Design: spec §8.5, §9.6, §12, §13.2.

**Status (2026-11-14):** built. The shadow rule has run on the live sessions since
16/11/2026; switching it on waits for S3.

## Milestone E3 — Re-ordering the main column

**Goal:** the trader can put the panels of the main column in the order that suits them.

**Built:** up and down buttons on each main-column panel; the order remembered, read
tolerantly, and reset by "Restore panels"; the index tabs and the option chain stay put.
Design: spec §13.2 (Panel order).

**Status (2026-11-16):** built, with unit tests; checked in a browser on the live feed.

## Milestone C1 — Editable, versioned config

**Goal:** the trader tunes the parameters in the app, can always get back to an earlier
set, and can see which set produced each signal.

**Built:** `config_versions` (migration 010), the highest version in force, a version
never rewritten (a revert is a new one); the edit form, the history with revert, and each
signal's `config_version` as a chip; the old reload button removed. Design: spec §3.2,
§12, §13.2 (Config control, ConfigVersionChip).

**Status (2026-11-16):** built, with unit tests; checked in a browser.

## Milestone E4 — BULLION tab

**Goal:** gold and silver on their own tab beside NIFTY and BANKNIFTY, with what Upstox
already provides.

**Built:** the MCX GOLD and SILVER near and next contracts picked each day from Upstox's
MCX file; a card per metal with the day's figures, liquidity, the contract's range and
limits, the next month and the gold/silver ratio. Display only at first (E6 added signals
and trades). Design: spec §6.6, §13.2.

**Status (2026-11-16):** built, with unit tests; checked by the owner on the live feed.

## Milestone E5 — NSE and MCX hours apart

**Goal:** bullion keeps MCX hours, and gold ticking never hides an index outage.

**Built:** index liveness from NSE ticks only; MCX hours and holidays (`mcx_open`,
`mcx_close`, `config/mcx-holidays.txt`); the bullion status (`live`, `stale`, `closed`,
`holiday`) in the health frame; the banner and the top bar following the tab; session
banners in amber. Design: spec §6.6 (Hours and liveness), §14.

**Status (2026-11-16):** built, with unit tests; checked on the live feed, including a
network drop while MCX was open.

## Milestone E6 — Bullion signals and paper trades

**Goal:** gold and silver get their own market view, signals and paper trades, on MCX
hours, without touching the index engines.

**Built:** the bullion bias (trend at first), buy and sell signals on the near future,
long and short paper trades priced by the contract's point value, GOLD, SILVER and bullion
rows in the Journal, `bullion_ticks` (migration 011) with a bullion replay, and the
bullion desk running `eval_offset_seconds` after each minute. Design: spec §6.6, §9a, §10,
§13.2.

**Status (2026-11-16):** built, with unit and replay tests. The bias, evidence and panels
were checked live; a live bullion paper trade is still to be seen.

## Milestone E7 — Live signal levels

**Goal:** while a signal waits for the trader, its entry, target and stop follow the
price, and a paper trade gets the levels that were on screen.

**Built:** the fired levels kept on the signal and the live ones worked out from the price
now, sent as `SignalOut.live` and a `signal_live` frame once a second; the card's Fired
and Live rows; a paper trade taking the live levels at its fill. Design: spec §9.3, §10.1.

**Status (2026-11-16):** built, with unit tests.

## Milestone E8 — Net volume per candle

**Goal:** see, minute by minute, whether buyers or sellers drove the traded volume.

**Built:** each tick's volume signed in the candle builder against the quote before it;
`bv` and `sv` on the candles and the near future's candles in the index response; a
net-volume pane under the price chart. Display only. Design: spec §7.1, §11, §12, §13.2.

**Status (2026-11-16):** built, with unit and replay tests.

## Milestone E9 — One Market view panel

**Goal:** the market view and the evidence that produces it in one full-width panel, with
the signal on its own row.

**Built:** "Market view" holding the meter with the evidence and the flow line under it;
the signal as its own panel; every panel moving on its own; an older stored layout carried
over. Design: spec §13.1, §13.2 (Panel order, PanelFrame).

**Status (2026-11-16):** built, with unit tests; checked in a browser.

## Milestone E10 — Headlines

**Goal:** a quick check on what is moving the market: Upstox headlines for the heaviest
NIFTY and BANK NIFTY stocks, newest first, under the option chain.

**Built:** the news poller (`market/news.py`) on Upstox's news API while logged in, from
the stocks in `config/news-stocks.txt`; the `news` frame; the Headlines panel under the
chain with its divider, day groups, unseen marks and index chips. Display only: nothing
reaches the bias or signals, nothing is stored. Design: spec §3.1, §6.7, §12.2, §13.1,
§13.2.

**Status (2026-11-17):** built, with unit tests.

## Milestone E11 — Sector indices, ATM in Details

**Goal:** see how the sectors behind the index are moving, beside spot and futures.

**Built:** the `sector_indices` setting (ten for NIFTY, three bank sub-indices for BANK
NIFTY), subscribed and recorded like VIX; `IndexStats.sectors`; the Sectors block on the
Index panel; ATM and the strike count moved into Details. Display only. Design: spec §3.1,
§7.4, §13.1, §13.2 (IndexTiles).

**Status (2026-11-17):** built, with unit tests.

## Milestone E12 — Macro evidence: dollar, crude, gold

**Goal:** the index and bullion biases take account of the dollar, the rupee, crude oil
and gold, live with a small weight.

**Built:** a dollar-index proxy rebuilt from NSE's currency futures; `MacroTracker` for
the currency futures and MCX crude; each market's move over `macro.window_minutes` scored
with its sign; a fourth evidence group, `macro`, with its own weight. Design: spec §3.2,
§6.8, §8.4, §8.6, §9a; signal.md §3.4, §4, §13.

**Status (2026-11-18):** built, with unit tests. The weights and full-strength moves are
starting values, to be tuned with `tools/score.py` on recorded weeks.

## Milestone E13 — Futures OI, order flow and the other metal in the bullion bias

**Goal:** the gold and silver bias reads more of what Upstox already sends for the near
future, not just its price.

**Built:** `futures_oi`, `net_volume` and `book_imbalance` in `indicators/futures.py`;
`BullionTracker.minute_book()`; the other metal's trend as `peer_metal`; a `flow` group
and `bullion_weights()`; a volume jump after a silence counted but not signed. Design:
spec §7.1, §8.4, §9a; signal.md §13.

**Status (2026-11-18):** built, with unit tests. Replayed on the MCX sessions of
16–18/11/2026 against the previous build: 168 bullion signals before, 80 after; SILVER
better (+0.04 % → +0.10 % per signal), GOLD worse (+0.04 % → −0.02 %). Too little data to
judge; the weights are starting values.

## Milestone E14 — GIFT Nifty opening gap in the NIFTY bias

**Goal:** NIFTY's bias takes account of how far the market moved overnight, as GIFT Nifty
shows it, for the first minutes after the open.

**Built:** GIFT Nifty fetched over REST once NSE opens (`market/gift.py`), stored per day
in `gift_nifty`; the overnight move scored at the open and fading over
`macro.gift_fade_minutes`; three `macro.gift_*` parameters. Design: spec §6.8, §8.6;
signal.md §3.4.

**Status (2026-11-19):** built, with unit tests; checked against Upstox on 19/11/2026.
Replayed on 16–18/11/2026 it changed no signal: in the macro group it moves NIFTY's bias by
at most about 0.02, so real influence needs a weight of its own, which is the owner's call.

## Milestone E15 — Factor switches in the Evidence panel

**Goal:** the trader can leave any factor out of an index's or metal's bias with a switch
on its Evidence row; every factor is on by default.

**Built:** `aggregate(off=...)`, giving a switched-off factor weight 0 and its share to the
live ones, and switches on the Evidence rows. Design: spec §8.4; signal.md §4, §11.

**Status (2026-11-19):** built, and superseded the same day by E16, which moved the
switches into the versioned config.

## Milestone E16 — Factor switches in the versioned config

**Goal:** the factor switches are parameters, so each signal's config version says which
factors were on; they are flipped in the Config control and shown read only in Evidence.

**Built:** `factors.nifty`, `factors.banknifty`, `factors.gold`, `factors.silver` in the
model; `ParameterService.set_factor` and `PUT /api/parameters/factors/{scope}/{name}`, one
version per flip; the Factors tab; read-only switches in Evidence; a test keeping the
names equal to the engines'. Design: spec §8.4; signal.md §4, §11.

**Status (2026-11-19):** built, with unit tests; checked by the owner in the app.

## Config drawer (19/11/2026, not a milestone)

**Goal:** the config is easier to read and edit: more room than a dropdown, and every
value explained where it is shown.

**Built:** a drawer on the right with three tabs, Parameters (help text and allowed range
under each value), Factors (a one-line explanation each) and Versions (the one in force
marked), closing on its button, the backdrop or Escape. Design: spec §13.2 (Config
control).

**Status (2026-11-19):** built, with unit tests; checked by the owner in the app.

## Milestone E17 — Paper bank account

**Goal:** paper trades are funded by a fake bank account. A trade opens only if the bank
can block its money, and its net P&L is deposited or deducted when it closes. The opening
balance is a parameter.

**Built:** `bank.opening_balance` and the metals' margin rates; `PaperBank`, one for every
market; the money a trade blocks and settles; `bank_ledger` (migration 015) with deposits
and withdrawals when the opening balance changes; `GET /api/bank` and the `bank` frame;
the bank strip on the dashboard and the ledger in the Journal. Design: spec §10.5.

**Status (2026-11-20):** built, with unit tests; checked end to end on the synthetic feed,
including a withdrawal, a refused trade and the deposit back.

## Milestone E18 — Pause bullion around US data releases

**Goal:** no GOLD or SILVER signal fires in a window around a US data release (CPI,
payrolls), where a 1-minute trend signal is mostly noise. The releases are a hand-kept
file; the window and what else it stops are parameters.

**Built:** `config/us-events.txt` and its loader; the `event_pause` gate; the window
parameters and the two switches (end a waiting signal, refuse a trade by hand); the reason
on the signal card. Design: spec §9a; signal.md §13.6, §13.8–13.10.

**Status (2026-11-24):** built, with unit tests.

## Logout (24/11/2026, not a milestone)

**Goal:** end the Upstox login on demand instead of waiting for the 03:30 expiry, and log
in again without restarting the app.

**Built:** `POST /api/auth/logout`, revoking the token at Upstox (best effort), deleting it
and closing the feed socket until the next login; Logout in the top bar, asking once before
it acts. Design: spec §4, §12.

**Status (2026-11-24):** built, with unit tests.

## Milestone E19 — Executed paper trades page

**Goal:** a page of the paper trades, where each one opens to why it was taken and how it
went: levels and fills, P&L, the signal, what the instrument did after it, and the
evidence at the minute it fired. Display only; nothing new is stored.

**Built:** `GET /api/paper-trades/{id}` with the trade and its signal; the Trades page
(`#trades`) with filters, open trades first at the live price with a Close button, closed
trades by day, and each trade's detail; the Journal keeping the bank and the summary cards.
Design: spec §12, §13.2 (Trades page).

**Status (2026-11-25):** built, with unit tests; checked by the owner in the app.

## Top bar redesign (25/11/2026, not a milestone)

**Goal:** the owner found the top bar scrolling sideways (Logout hidden off the edge at
1440 px), the items after the feed's tick age jumping as the number changed width, and
every control looking the same.

**Built:** the bar in groups (the brand linking home, the status strip, the page tabs, the
dashboard's tools, the app's tools, Login or Logout on its own); a fixed-width tick age;
the Config button showing the version only; wrapping instead of scrolling. Design: spec
§13.1, §13.2.

**Status (2026-11-25):** built, with unit tests; checked by screenshot at 1440, 1280 and
1024 px, dark and light.

## Performance pass (25/11/2026, not a milestone)

**Goal:** the owner asked for a performance review with changes that keep behaviour and
look as they are. Measured on the running app first: the backend had headroom; the cost
was in the browser, plus two bugs.

**Built:** latency sampled with one animation-frame callback per paint; `App` no longer
reading the slices that change with the frames; one shared clock per interval; SQLite
incremental vacuum, with `make compact` for an older file. Design: spec §10.4, §11, §14a.

**Status (2026-11-25):** built, with unit tests. `make compact` is not yet run on the live
database (it needs the app stopped).

## Review fixes (26/11/2026, not a milestone)

**Goal:** the owner asked for a code review and its five most important issues, fixed.
Each fix started with a test that failed on the old code.

**Built:** routes made `async` so they run on the event loop; the chain closing its minute
before the candles drive the bias; a late tick no longer reopening a flushed candle;
Logout during a reconnect; the gate reasons sent with the bias of the same minute.
Design: spec §7.1, §12.1.

**Status (2026-11-26):** built, with tests.

## Frontend review fixes (26/11/2026, not a milestone)

**Goal:** the owner asked for a review of the frontend and its five most important issues,
fixed. Each fix started with a test that failed on the old code.

**Built:** market time on the page (`lib/marketClock.ts`, re-based on each frame's
`t_mkt`, so a replay reads as the recorded day); the config-version tooltip; busy state per
row; the "applies from" minute after a save; a price flash no longer stuck. Design: spec
§12.2.

**Status (2026-11-26):** built, with tests.

## Milestone E20 — Paper trades opened by hand

**Goal:** open a paper trade with no signal (enhancement 23): any option in the chain
window, or a metal's future either way, with the signal rule's target and stop or the
trader's own; change the levels of any open trade; keep these trades out of the signal
stats.

- Migration `016_paper_trade_levels.sql`: `paper_trade_levels` (every set of levels a trade
  has had) and `paper_trades.levels_edited`. A trade opened by hand stores
  `MANUAL_SIGNAL_ID = 'manual'` as its `signal_id`, so `paper_trades` needs no new column.
- `engine/signals.py`: the option level rule moves out of `_fire` into `levels_for` (with
  `_delta` shared by the live levels); `manual_contract` and `default_levels` serve a trade
  by hand. `ManualContract` describes what it is in. `engine/bullion_signals.py`: the same
  through `future_levels`.
- `engine/paper.py`: the entry gates in one `_entry_gate`, with the signal cut-off from
  `PaperRules.last_entry` for a trade by hand; `quote_manual` (the ticket, never opens),
  `open_manual`, `set_levels`; `check_levels` (target and stop either side of the price);
  each open and change writes a levels row; `journal_stats` adds the `manual` scope and
  keeps those trades out of the others.
- `api/paper.py`: `GET /paper-trades/ticket`, `POST /paper-trades/manual`,
  `PATCH /paper-trades/{id}/levels`; `PaperTradeOut` gains `manual` and `levels_edited`,
  the detail gains `levels`; `POST /paper-trades` refuses the manual id.
- Frontend: `TradeTicket` (dialog), `LevelsEditor` (Open paper trades and the Trades page,
  each open row's Levels button), `lib/ticket.ts`; the option chain's prices and the
  bullion cards' Buy / Sell open the ticket from `ChainPanel` and `BullionTilesPanel`; a
  "manual" badge, a `*` on changed levels, "Opened by hand" in the detail and the Journal,
  and the levels history on the Trades page.
- Tests: `tests/test_manual_trades.py` (a quote and an open at any strike; slippage from
  the ticket; typed and partly typed levels; levels the fill has passed; every gate
  including both cut-offs, the bank and the US pause; levels matching a signal's on a
  normal and an expiry day; unknown contracts; no price; five-paise options; stop, close
  and restart; editing a signal trade and a hand trade, refusals, the history; property
  tests that the default option and future levels bracket the fill; the journal scope;
  the API routes for an index option and a GOLD future). Vitest for the ticket, the
  editor, the chain and bullion buttons, Open paper trades, the Journal card and the
  Trades page detail.

- Follow-up (enhancement 24): targets and stops in whole rupees everywhere.
  `signals.py:round_rupee` / `round_levels` (half up; a level rounded onto the entry moves a
  rupee out; the 0.05 stop floor) used by the percentage and points rules, `rescale_levels`
  and `future_levels`; typed and edited levels rounded before they are checked. The level
  boxes step by a rupee. `tests/test_level_rounding.py` (table-driven and a property test
  that rounded levels are whole and bracket the entry) and the existing level tests
  updated to whole rupees.

**Demo:** on NIFTY, click a call's price two strikes above ATM in the option chain: the
ticket shows the price, money and the signal rule's levels; open it. Click a put's price,
type your own stop, open it. On BULLION, Sell GOLD. In Open paper trades, Levels on a
trade, change the target; it closes there. The Journal has an "Opened by hand" card; the
Trades page shows the trades badged "manual", with "Opened by hand" and the levels history
in the detail.

**Status (2026-11-26):** built, with unit tests; `make check` green. End-to-end check in
the running app to be asked of the owner.

## Milestone E21 — Gold BeES and Silver BeES on the BULLION tab

**Goal:** show the NSE gold and silver ETFs under their metals on the BULLION tab
(enhancement 25), display only.

- `config.py`: `bullion_etfs` (metal → symbol and `NSE_EQ` key), GOLDBEES and SILVERBEES.
- `market/etfs.py`: `EtfQuote`, `EtfSnapshot`, pure `etf_snapshot`, `EtfTracker` (latest
  merged tick and the day's range), `etfs_from` (none on synthetic) and `enrich_etfs`
  (start quote and 52-week range, each failing soft). `market/bullion.py` shares
  `day_position`, `year_range`, `widen_day`, `pct` and `diff` with it.
- `market/session.py`: `_load_etfs` / `attach_etfs` in a new `_load_side_markets`
  (bullion, macro, ETFs, GIFT Nifty, moved out of `_start`); the ETF keys are subscribed;
  their ticks keep the NSE path (`prices`, `ticks`). `api/bullion.py`: `BullionEtfOut`,
  `BullionOut.etfs`; `api/ws.py`: an ETF tick marks the `bullion` frame due.
- Frontend: `BullionEtfOut` in `api/types.ts`; `BullionCards` puts an `EtfCard` under each
  metal (shared Details toggle, `DetailsToggle`; "NSE closed" note from `market_status`,
  passed by `BullionTilesPanel`).
- Tests: `tests/market/test_etfs.py` (the default setting, none on synthetic, table-driven
  snapshot maths, the 52-week range widened by today, the tracker's merge and day range,
  the start data and its failing soft, the API, `ticks` and the `bullion` frame). Vitest
  for the ETF cards: order under the metals, details, no trade buttons, the NSE note.
- Test fixes found on the way: `test_level_rounding`'s property test generated a short
  future whose target was zero (it failed on main once Hypothesis found it), and
  `test_net_volume` raced the synthetic feed for the volume baseline.

**Demo:** on the live feed during NSE hours, open BULLION: GOLDBEES under GOLD and
SILVERBEES under SILVER, ticking; Details opens all four cards. After 15:30 the ETFs keep
their close with "NSE closed" while the futures tick on.

**Status (2026-11-26):** built, with unit tests; `make check` green. Accepted by the owner
without an end-to-end check in the running app.

## Milestone E22 — Rates strip under the top bar

**Goal:** NIFTY, SENSEX, GOLD, SILVER, GOLDBEES and SILVERBEES with price and day change %
in a strip under the top bar on every page; a click opens the tab (enhancement 26).

- `market/stats.py`: `SENSEX_KEY` (`BSE_INDEX|SENSEX`), `STRIP_QUOTES`, `MarketQuote`,
  pure `market_quotes`; `market_wide_keys` subscribes SENSEX.
- `api/stats.py`: `QuoteOut`, `all_quotes`, `GET /api/quotes`. `api/ws.py`: `quotes` in
  `hello`; a SENSEX tick marks a throttled `quotes` frame due (`_push_quotes`); the
  no-client reset moved to `_drop_pending`.
- Frontend: `QuoteOut` / `QuotesFrame`, the store's `quotes` and `applyQuotes`;
  `lib/rates.ts:stripRates`; `components/RatesStrip`; `LiveRatesStrip` in `Live.tsx`
  between the top bar and the banner; `App`'s `openRate` selects the tab and metal and
  goes to the dashboard.
- Tests: `tests/market/test_quotes.py` (the key, the change maths with and without a
  previous close, the API following ticks, the `quotes` frame); the market-wide keys test
  takes SENSEX. Vitest: `stripRates` (order, changes, click targets, nothing known, no
  BULLION tab), `RatesStrip` (text, colours by sign, clicks, SENSEX not a button) and
  `App` (the strip shows ticks and quotes without re-rendering the page).

**Demo:** on the live feed, the strip under the top bar shows all six rates ticking; click
GOLDBEES on the Journal page: the dashboard opens on BULLION with GOLD in focus.

**Status (2026-11-26):** built, with unit tests; `make check` green. Accepted by the owner
without an end-to-end check in the running app.

## Milestone E23 — Hover previews on Trades, Data and Latency

**Goal:** a read-only card on hovering the Trades tab (open trades), Data (stored data) and
Latency (latency numbers), with clicks unchanged (enhancement 27).

- `components/HoverCard`: the shared card (`OPEN_DELAY_MS` 250, `CLOSE_DELAY_MS` 150;
  keyboard focus via `:focus-visible`; Esc and a click close it; `card` null shows none).
- `OpenTrades.tsx:OpenTradesPeek` (pure) and `LiveTradesPeek` in `Live.tsx` (reads the
  store's trades, mounted only while open), passed to `TopBar` as `tradesPeek` and put on
  the Trades tab by `PageTabs`.
- `DataPanel`: `DataPeek` (fetches the usage once) and `UsageTable`, shared with the panel.
- `DebugOverlay`: `useMetrics` (the 2 s fetch) shared by the overlay and `LatencyPeek`.
- Tests (Vitest): `HoverCard` (delay, a pass across opens nothing, moving into the card,
  Esc, click, nothing to preview); `OpenTradesPeek` (all markets, closed left out, total,
  none open, no live P&L yet); the Data card's figures and none once the panel is open;
  `LatencyPeek` (p95 against budget, over budget red, no samples); `TopBar` (the Trades and
  Latency cards, and none on the Trades page or with the overlay on).
- Code comments' enhancement tags corrected: the ETF code read `(E21)` and the rates strip
  `(E22)`, which are other enhancements' numbers; they are `(E25)` and `(E26)`.

**Demo:** hover Trades with two trades open: both are listed with live P&L and a total.
Hover Data: the stored figures. Hover Latency: p95s against budgets. Click Latency: the
overlay opens and hovering shows no card.

**Status (2026-11-26):** built, with unit tests; `make check` green. Accepted by the owner
without an end-to-end check in the running app.

## Milestone E24 — GOLDM and SILVERM, and lots per contract

**Goal:** each metal can trade its mini; default lots per contract, changeable on the
ticket (enhancement 28).

- `parameters/model.py` (`Bullion`): `gold_contract`, `silver_contract` (choices),
  `gold_lots`, `goldm_lots`, `silver_lots`, `silverm_lots` instead of `lots`;
  `contract_for`, `lots_for`; a before-validator reads a stored `lots` as all four.
  `config/params.toml` seeds them.
- `market/bullion.py`: `MINIS`, `CONTRACTS` (what the MCX file is read for, live and in
  replay); `BullionContract.mini` / `mini_quote`; the tracker subscribes the mini and
  `instrument(metal, contract)`; `MiniSnapshot` on `MetalSnapshot.mini`; the start quote
  covers the minis.
- Engines: `ManualContract.product`; `manual_contract(..., contract)`; `trade_contract(s)`
  (the index engine: the signal's option; the bullion engine: the configured contract).
  `engine/paper.py`: a signal trade opens `trade_contract`; `PaperRules.lots(p, contract)`;
  `quote_manual` / `open_manual` take `contract` and `lots` (1 to 100).
- API: ticket `contract`, `lots`; manual body `contract`, `lots`; `BullionMiniOut`;
  `SignalOut.trade`.
- Frontend: `BullionMiniOut`, `SignalTradeOut`, `TicketTarget.contract` / `lots`;
  `MiniCard` and shared `TradeButtons` in `BullionView`; the ticket's Lots box
  (`lib/ticket.ts:parseLots`) and the mini's live price in `BullionTilesPanel`; "trades
  GOLDM ×3" on the SignalCard; `instrumentLabel` names a mini.
- Tests: `tests/test_bullion_contracts_params.py` (defaults, choices per metal, bounds, a
  stored `lots`, the editor); `tests/market/test_bullion.py` (each metal's mini, none in
  the file, the mini tracked and shown, its start quote); `tests/test_bullion_minis.py`
  (a signal opening the mini with its lots and exits on the mini's ticks, default lots
  for the full contracts, a mini not loaded, hand trades with default and typed lots,
  bad lots, another metal's contract, the API end to end). Vitest for the mini card, the
  ticket's lots, the signal card's line and the label.

- Follow-up (enhancement 29): the BULLION tiles show only the metal in focus.
  `BullionCards` takes `metal` (passed by `BullionTilesPanel` from `App`'s MetalSwitch
  choice): that metal's card across the panel, its mini and ETF beside each other under
  it; every metal when none is given. Vitest: gold only, silver only, no focus.

- Follow-up (enhancement 30): the mini cards get the metal cards' Details. A mini is a
  `BullionContract` of its own (`mini: BullionContract`, near and next, quote, year range;
  `enrich` covers it), its day range is tracked apart from the metal's candles and book,
  and `MetalSnapshot.mini` is a `MetalSnapshot` (`MiniSnapshot` removed), with
  `point_value` on every snapshot. The frontend renders the mini with `MetalCard`
  (`metal` = the metal it trades as). Tests: the mini's figures, next month and start
  quote, `enrich` for the mini, and its Details.

- Follow-up (enhancement 31): each bullion card's Details opens on its own.
  `BullionView.tsx:useDetails(card)` keeps one remembered choice per card
  (`tradedisha.bullionDetailsOpen.<card>`) in `MetalCard` and `EtfCard`, in place of the
  one choice `BullionCards` passed to every card. Vitest: one card opens, the others stay
  closed, closing one leaves another open, each remembered.
- Test fix found on the way:
  `test_net_volume.py::test_the_futures_candle_frame_carries_net_volume` failed when run
  before about 12:20 IST. Its ticks were 700 minutes ahead within the same day, so the gap
  fill sent hundreds of candle frames at once and the hub dropped the socket as a slow
  client. They are now two minutes ahead and fed in one call.

**Demo:** in Config, Bullion, set `gold_contract` GOLDM and `goldm_lots` 3. On BULLION, the
GOLDM card shows under GOLD; a GOLD signal's card reads "trades GOLDM ×3" and its Paper
trade opens GOLDM ×3. Sell on the SILVERM card, type 2 lots: the ticket's quantity and
money follow; open it.

**Status (2026-11-27):** built, with unit tests; `make check` green. Accepted by the owner
without an end-to-end check in the running app.

## Milestone E25 — Tabs by exchange: NSE and MCX

**Goal:** the dashboard's tabs grouped by exchange, NSE (NIFTY, BANKNIFTY, BULLION with the
ETFs) and MCX (GOLD, SILVER), in place of one BULLION tab with a metal switch
(enhancement 32). Frontend only.

- `state/store.ts`: `ETF_TAB` and `METAL_TABS` in place of `BULLION_TAB`; a selected
  bullion tab survives a hello and falls back to the first index once the snapshot lacks
  its data (`bullionTabGone`).
- `lib/tabs.ts`: `tabGroups`, `tabIds`. `IndexTabs` draws the groups with their labels.
- `App.tsx`: the MCX tab is the metal in focus; NSE's BULLION renders `EtfTilesPanel`
  alone and no chain; `MetalSwitch` and `lib/useBullionMetal.ts` removed.
- `BullionView`: `BullionCards` without the ETFs (metal and mini side by side);
  `EtfCards` for NSE's BULLION. `Live.tsx`: `EtfTilesPanel`; `BullionTilesPanel` titled by
  its metal. `panelSummary.ts`: `bullionSummary(bullion, metal)`, `etfSummary`.
- `lib/rates.ts`: a rate's `tab` is the metal's or `ETF_TAB` (no `metal`); `RatesStrip`'s
  `onOpen(tab)`.
- Tests (Vitest): `lib/tabs.test.ts`, `IndexTabs.test.tsx`, the store's fallbacks, the
  MCX and ETF cards, the summaries, the rates' tabs, and `App` (the groups; NSE BULLION
  shows the ETFs alone and no chart; MCX GOLD shows its metal and chart, no switch).

**Demo:** on the live feed the tab row reads `NSE [NIFTY] [BANKNIFTY] [BULLION] │ MCX
[GOLD] [SILVER]`. NSE BULLION shows the two ETF cards alone; MCX SILVER shows the SILVER
and SILVERM cards, its signal, view, chart and trades. Click GOLDBEES on the rates strip:
NSE BULLION opens.

**Status (2026-11-27):** built, with unit tests; `make check` green. Accepted by the owner
without an end-to-end check in the running app.

## Milestone E26 — The Journal as the bank statement; the summary on Trades

**Goal:** the summary cards move from the Journal to the Trades page, under the executed
trades. The Journal becomes the paper bank's full statement: every cash move with the
running figures (enhancement 33).

- `engine/bank.py`: `StatementRow`, pure `build_statement(ledger, trades)` and
  `PaperBank.statement(start_ms, end_ms, kinds, index)`. It is worked out from `bank_ledger`
  and the funded `paper_trades`, with no migration.
- `api/paper.py`: `GET /api/bank/statement` (`StatementRowOut`, `BankStatementOut`).
- Frontend: `JournalStats` (the cards, moved out of `Journal`) under the `TradeLog`
  table, following its market and dates. `Journal` rewritten as the statement with
  market, kind and date filters, refetched on a trade change or a new cash move. `Bank`
  loses its ledger table (`showLedger`). The `TradeLog` table folds away (`usePref`,
  `tradedisha.tradeTableOpen`), and each trade's first cell carries a neutral call / put /
  long / short tag (`lib/direction.ts:sideTag`, `instrumentName`) instead of green or red
  (enhancement 34).
- Tests: `test_bank.py` (block then settlement, cash moves, the opening deposit first
  whatever the clocks, unfunded trades left out, filters keep the running figures, a
  hypothesis property that the statement ends at the summary, the endpoint).
  `Journal.test.tsx`, `JournalStats.test.tsx`, and `TradeLog.test.tsx` (the cards follow
  market and dates, not exit or fill; the side tags; folding the table).

**Demo:** open and close a paper trade, then raise the opening balance in Config. The
Journal lists Opening deposit, Blocked, Settled and Deposit with the balance and available
after each. The Trades page shows the summary cards under the trades, and picking GOLD
narrows both.

**Status (2026-11-27):** built, with unit tests; `make check` green.

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
   gold and silver were added in E4 and E6, and their minis in E24; SENSEX is shown as a
   rate since E22, not traded.)

## Working agreements

- Each milestone starts with a short written note of what will be built and ends with a
  demo against the goal above; anything that fails the demo is fixed before moving on.
- Defaults chosen by the builder (weights, thresholds, strike width, costs) live in the
  parameter model with a description each, so they are visible and easy to change in the
  app's config editor; `config/params.toml` seeds a new database with them.
- No real-order code path is ever added, even behind a flag.
