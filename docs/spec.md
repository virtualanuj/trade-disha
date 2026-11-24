# TradeDisha — Architecture and Design Specification

Requirements: [intent.md](intent.md). Milestones: [plan.md](plan.md). A walkthrough of how
a signal is worked out, with examples: [signal.md](signal.md). Terms: [dd.md](dd.md).
This document describes how the application is built, including the enhancements after
1.0.0 (milestones are named where a section came from one). Values marked *(default)* live
in configuration and can be changed without code changes.

---

## 1. System overview

```
 Upstox REST ──► Auth, instruments, quotes, candles (backfill)
 Upstox WS ────► Feed adapter ─┐            (or Replay / Synthetic provider)
                               ▼
                           Tick bus (synchronous fan-out)
          ┌───────────────┬────┴──────────┬───────────────┬──────────────────┐
          ▼               ▼               ▼               ▼                  ▼
     Tick store      Candle builder   Chain state    Order flow       Bullion tracker
   (ticks; bullion        │          (NSE options)  (futures, ATM)   (MCX GOLD/SILVER,
    to bullion_ticks)     ▼ minute close   │              │           own candles)
                      Bias engine ◄────────┘              │                 │ +20 s
                          │                               │                 ▼
                          ▼                               │           Bullion desk:
                      Signal engine (live + shadow) ◄─────┘           bias → signals →
                          │                                           paper trades
                          ▼                                                 │
                      Paper trade manager, outcome tracker                  │
                          │                                                 │
                          ▼                                                 ▼
          listener lists on FeedSession (candle, bias, signal, trade, bullion) ──► WS hub
          EventBus (low-rate state: feed health, auth, window, parameters, news)► WS hub
                                                                                 │
                                                       HTTP + WS (localhost)     ▼
              Frontend (React, single page): top bar, NIFTY / BANKNIFTY / BULLION tabs,
              panels, option chain, Journal page
```

Single process, single user, runs on the trader's Mac. All state is in memory during the
session and persisted to one SQLite file. The frontend never talks to Upstox directly.

### 1.1 Principles
- **One way in for market data.** Every tick enters through the `MarketDataProvider`
  interface. Live (Upstox), replay (recorded ticks), and test (synthetic) providers are
  interchangeable.
- **Pure computation.** Indicators, aggregation, and signal rules are pure functions of
  their inputs. Side effects (persistence, push) happen in thin orchestrators.
- **Event-driven push.** Per-tick and per-minute data (candles, bias, signals, trades,
  bullion) reaches the WebSocket hub through callback lists on `FeedSession`; low-rate
  state changes (feed health, auth, strike window, parameters, headlines) go through the in-process
  `EventBus`. The frontend never polls for live data.
- **Explainability is data.** Every bias and signal carries its full indicator breakdown
  as a structured object, persisted alongside it.
- **No real-order code path.** There is no module, flag, or endpoint that can place an
  order with the broker.

---

## 2. Repository layout

```
TradeDisha/
├── backend/
│   ├── pyproject.toml
│   ├── tradedisha/
│   │   ├── config.py            # Settings (pydantic-settings, TRADEDISHA_* from .env)
│   │   ├── main.py              # app factory; build_state() wires every long-lived object
│   │   ├── app_state.py         # AppState, hung on app.state.td
│   │   ├── clock.py             # MarketClock (NSE and MCX), DrivenClock for replay
│   │   ├── events.py            # EventBus for low-rate state changes
│   │   ├── auth/                # Upstox OAuth, token store
│   │   ├── instruments/         # master download and parsing, resolution, expiry rules
│   │   ├── feed/                # provider interface, upstox (+ protobuf), replay, synthetic, tick bus
│   │   ├── market/              # FeedSession, candles, chain, flow, backfill, bullion tracker,
│   │   │                        # macro tracker, GIFT Nifty, news, index stats
│   │   ├── indicators/          # pure indicator functions, series maths, delta
│   │   ├── engine/              # bias, aggregator, signals, outcomes, paper trades, bullion desk
│   │   ├── parameters/          # ParameterSet model, field schema, versioned service
│   │   ├── metrics/             # latency samples, event-loop lag
│   │   ├── store/               # SQLite connection, migrations, tick store
│   │   ├── tools/               # score.py: replay recorded days into a scorecard
│   │   └── api/                 # REST routers, WS hub, schemas
│   └── tests/                   # mirrors the package; replay and API tests at the top level
├── frontend/
│   ├── package.json
│   └── src/
│       ├── api/                 # REST client, WS client, hand-written types
│       ├── state/               # Zustand store
│       ├── lib/                 # formatting, panels, prefs, latency, direction, summaries,
│       │                        # config form helpers, factor names and help, news
│       ├── theme/               # dark/light theme
│       └── components/          # one folder per component, test beside it: TopBar,
│                                # IndexTabs, IndexTiles, BullionView, BiasMeter, PriceChart,
│                                # SignalCard, EvidenceTable, OpenTrades, SignalHistory,
│                                # OptionChain, Journal, ConfigControl, DataPanel,
│                                # StatusBanner, PanelFrame, SidePanel, RightColumn,
│                                # Headlines, Divider, DebugOverlay, FactorSwitch, FlowLine,
│                                # ConfigVersionChip, Facts, …
├── config/
│   ├── params.toml              # starting parameters for a new database
│   ├── nse-holidays.txt         # NSE trading holidays
│   ├── mcx-holidays.txt         # MCX holidays and evening-only days
│   ├── us-events.txt            # US data releases that pause bullion signals (E18)
│   └── news-stocks.txt          # stocks whose news fills the Headlines panel (E10)
├── data/                        # SQLite files, instrument caches (gitignored)
├── scripts/check.sh             # every gate, run by `make check`
└── docs/
```

---

## 3. Configuration

Two kinds of configuration, deliberately separated:

- **Static settings** (`config.py`, pydantic-settings, from environment / `.env`): things
  that need a restart and are not about the algorithm. Credentials, paths, which indices,
  market hours, bind address.
- **Tunable parameters** (`ParameterSet`, stored as numbered versions in the database):
  everything that shapes a recommendation. Edited in the app; each save is a new version
  applied at the next minute close. See §3.2.

### 3.1 Static settings

Fields of `config.py:Settings`, set as `TRADEDISHA_<NAME>` in the environment or `.env`.

| Setting | Default | Notes |
|---|---|---|
| `upstox_api_key`, `upstox_api_secret`, `upstox_redirect_uri` | —, —, `http://127.0.0.1:8000/api/auth/callback` | required for the live feed |
| `feed_provider` | `synthetic` | `synthetic`, `replay` or `upstox` |
| `db_path`, `data_dir` | `data/tradedisha.sqlite`, `data/` | live recordings usually use `data/live.sqlite` |
| `indices` | `NIFTY, BANKNIFTY` | |
| `sector_indices` | NIFTY: Auto, FMCG, IT, Pharma, Metal, Energy, Realty, Media, Fin Service, PSU Bank; BANKNIFTY: PSU Bank, Pvt Bank, Fin Service | Upstox `NSE_INDEX` names (`"Nifty Auto"`) per index; JSON in the environment; subscribed at start, so a change needs a restart (§7.4) |
| `market_open`, `market_close`, `pre_open_start` | 09:15, 15:30, 09:00 | NSE, IST |
| `holidays_file` | `config/nse-holidays.txt` | |
| `mcx_open`, `mcx_close` | 09:00, 23:30 | MCX; set the close to 23:55 while the US is on standard time |
| `mcx_holidays_file` | `config/mcx-holidays.txt` | `YYYY-MM-DD` closed, `YYYY-MM-DD HH:MM` opens late |
| `us_events_file` | `config/us-events.txt` | `YYYY-MM-DD HH:MM label`, IST: US data releases that pause bullion signals (§9a) |
| `news_stocks_file` | `config/news-stocks.txt` | headlines (§6.7); how often is the `news.poll_seconds` parameter (§3.2) |
| `enforce_signal_hours` | unset | unset = enforce unless the feed is synthetic |
| `feed_live_max_tick_age_ms` | 5000 | index liveness (§14) |
| `bullion_live_max_tick_age_ms` | 15000 | bullion liveness (§6.6) |
| `risk_free_rate` | 0.065 | for computed delta |
| `strike_window`, `recenter_strikes` | 10, 2 | starting values; the `chain` parameters (§3.2) govern |
| `replay_date`, `replay_speed`, `replay_drop`, `replay_bullion` | latest, 1.0, none, false | §6.3, §9a |
| `synthetic_ticks_per_second`, `synthetic_seed`, `synthetic_trend_per_tick` | 2.0, none, 0.0 | synthetic feed |
| `ws_tick_hz`, `ws_chain_hz` | 20, 2 | WebSocket throttles (§12.2) |
| `bind_host`, `bind_port` | 127.0.0.1, 8000 | |
| `serve_frontend`, `frontend_dist`, `frontend_url`, `reload`, `cors_origins` | false, `frontend/dist`, `http://localhost:5173`, true, Vite's origins | how the app is served (`make start` vs `make backend`) |
| `params_path` | `config/params.toml` | seeds version 1 of the parameters |

All times are IST. The backend runs with `Asia/Kolkata` as its working timezone and stores
UTC epoch milliseconds.

### 3.2 Tunable parameters (`ParameterSet`)

A single pydantic model with validation (weights sum to 1, thresholds in range, fast EMA <
slow EMA, …). Names below are the model's paths (`weights.trend`, `bullion.lots`, …), grouped
by section. Each field carries a one-line description, which the editor shows as help text.

| Group | Parameter | Default |
|---|---|---|
| Weights | `trend`, `oi`, `premium` | 0.40, 0.35, 0.25 |
| Weights | `expiry_oi_weight_factor` | 0.5 |
| Weights | `macro` | 0.10 (E12: share of the bias for the macro group; the three above keep their proportions in the rest, so 0.36 / 0.315 / 0.225 / 0.10; §8.6) |
| Macro | `window_minutes`, `max_age_seconds` | 30, 180 |
| Macro | `dollar_full_pct`, `usdinr_full_pct`, `crude_full_pct`, `gold_full_pct` | 0.15, 0.10, 0.80, 0.40 (% move over the window that counts as full strength) |
| Macro | `gift_full_pct`, `gift_fade_minutes`, `gift_direction` | 0.50, 30, `follow` (or `fade`); NIFTY only (E14, §8.6) |
| Bias | `entry_threshold` | 0.50 |
| Bias | `neutral_band` | 0.20 |
| Bias | `setup_threshold` | 0.35 (trigger rule; see §9.6) |
| Bias | `rearm_hysteresis` | 0 (off; see §9.1) |
| Flow | `window_seconds`, `trigger_score`, `hold_seconds` | 15, 0.25, 5 (see §8.5, §9.6) |
| Flow | `w_fut_book`, `w_fut_trades`, `w_options` | 0.4, 0.3, 0.3 |
| Trend | `ema_fast`, `ema_slow`, `ema_k` | 9, 21, 8 |
| Trend | `vwap_full_pct` | 0.3 |
| Trend | `supertrend_period`, `supertrend_mult`, `supertrend_ramp_bars` | 10, 3.0, 3 |
| OI | `pcr_strike_range`, `pcr_centre`, `pcr_full_dev` | 5, 1.0, 0.5 |
| OI | `oi_change_strike_range` | 2 |
| OI | `maxpain_drift_minutes`, `maxpain_full_steps` | 15, 2 |
| Premium | `premium_roc_minutes`, `premium_roc_full_spread` | 5, 20 |
| Premium | `iv_change_minutes`, `iv_full_change` | 15, 2.0 |
| Premium | `confirmation_minutes`, `divergence_score` | 5, −0.5 |
| Signal | `signal_ttl_seconds` | 300 |
| Signal | `target_pct`, `stop_pct` | +30, −15 |
| Signal | `expiry_points` (per index: target/stop) | NIFTY 40/20, BANKNIFTY 100/50 |
| Signal | `outcome_horizon_minutes` | 30 (see §9.5) |
| Signal | `entry_mode` | `minute_close` (or `trigger`; see §9.6) |
| Signal | `max_spread_pct` | 1.0 (trigger rule) |
| Signal | `last_signal_time`, `last_signal_time_expiry` | 15:00, 13:00 |
| Chain | `strike_window`, `recenter_strikes` | 10, 2 (**not read**: the chain uses the process settings `TRADEDISHA_STRIKE_WINDOW` / `TRADEDISHA_RECENTER_STRIKES`, §3.1; open item in enhancements.md) |
| Paper | `square_off_time` | 15:15 |
| Paper | `cost_per_trade` | ₹60 |
| Paper | `lots` | 1 |
| Bank | `opening_balance` | ₹25,00,000 (E17; raising it deposits the difference, lowering it withdraws, §10.5) |
| Bullion | `signals` | `on` (`off` = no bullion signals) |
| Bullion | `entry_threshold`, `neutral_band`, `rearm_hysteresis` | 0.60, 0.20, 0 |
| Bullion | `signal_ttl_seconds`, `eval_offset_seconds` | 300, 20 |
| Bullion | `first_signal_time`, `last_signal_time`, `square_off_time` | 09:15, 22:45, 23:00 |
| Bullion | `target_pct`, `stop_pct` | 0.40, 0.20 (% of the future's price) |
| Bullion | `lots`, `cost_fixed_per_lot`, `cost_pct_of_value` | 1, ₹60, 0.012 % |
| Bullion | `gold_margin_pct`, `silver_margin_pct` | 10, 12 (E17: % of value a future blocks in the paper bank, §10.5) |
| Bullion | `macro_weight` | 0.10 (E12, E13: other markets' share, the dollar and the other metal) |
| Bullion | `oi_weight`, `flow_weight` | 0.15, 0.15 (E13; trend has what OI, flow and macro leave) |
| Bullion | `oi_window_minutes`, `oi_full_pct`, `oi_price_flat_pct`, `oi_unwind_factor` | 15, 0.50 %, 0.02 %, 0.5 |
| Bullion | `flow_window_minutes`, `flow_trades_full`, `flow_book_minutes`, `flow_book_full` | 15, 0.50, 30, 0.20 |
| News | `poll_seconds` | 180 (30–3600; display only, §6.7; applies at once, not at a minute close) |
| Factors | `factors.nifty`, `factors.banknifty`, `factors.gold`, `factors.silver`: one value per factor | `on` (or `off`; E16, §8.4; flipped in Config → Factors, not in the typed form) |

**Versions (Milestone C1).** The database is the source of truth. Table
`config_versions` holds every saved set: `version` (1, 2, 3, …), `tag` (typed by the
trader, required, at most 60 characters), `created_ts`, `source` (`seed`, `edit` or
`revert`), `reverted_from` and `params_json` (the whole set). Versions are never changed
or deleted, and the highest one is in force.

- **Start.** `ParameterService.load()` reads the highest version. A database with none
  takes version 1 from `config/params.toml` (tag "initial"); if that is needed and the
  file is missing or invalid the app refuses to start. After that the file is not read
  again: editing it changes nothing. If the stored version no longer validates (a later
  build changed the model), a new version is saved from the file with a tag saying so.
- **Edit.** `PUT /api/parameters` validates the whole set and saves it as the next
  version; on failure it returns 422 with the field errors and nothing changes. A save
  with no change or without a tag is refused the same way.
- **Revert.** `POST /api/parameters/versions/{n}/revert` saves version n's values as a new
  version (tag "Revert to vN" unless one is given), so history is only ever added to.
- Each change publishes `ParametersChanged`, which sends the `parameters` frame.
- **Per database.** Live and synthetic data use separate database files (§6), so each has
  its own version history. The offline scoring tool replays into a fresh scratch
  database, which is seeded from the file given with `--params`.
- **Signals.** `signals.config_version` references `config_versions(version)`: the
  version in force when the signal fired, for live and shadow signals alike. It is null
  for signals from before versions existed.

**Application.** The Signal Engine and Paper Trade Manager read the active set at the
start of each minute-close evaluation, so a save takes effect at the next minute, never
mid-computation. Open paper trades keep the target/stop they were opened with.
Chain-window parameters (`strike_window`, `recenter_strikes`) take effect at the next
re-centre check. `news.poll_seconds` applies as soon as it is saved: the poller re-reads it
and the next fetch falls due that long after the last one (at once, if that is past); a
save never fetches early.

**Starter file.** The repository ships `config/params.toml` with the defaults above,
commented. It supplies version 1 for a new database and is what the tests and the scoring
tool start from.

---

## 4. Authentication (Upstox OAuth)

Upstox issues an access token valid until ~03:30 IST the next day, so login is a daily
manual step.

- `GET /auth/login` → 302 to Upstox authorisation URL with `client_id`, `redirect_uri`,
  `state`.
- `GET /auth/callback?code=…&state=…` → exchanges code for access token via Upstox token
  endpoint; stores `{token, obtained_at, expires_at}` in `sessions`; publishes
  `AuthChanged("valid")`; starts the feed (`FeedSession.start()`, 502 if it fails); then
  redirects to `/` when the backend serves the frontend, else to `frontend_url`. (Both
  routes sit under `/api`, like every REST route.)
- `AuthState` is one of `missing | valid | expired`. Computed from `expires_at` and
  confirmed by a cheap profile call at startup.
- When `AuthState != valid`, the feed adapter does not connect, the top bar shows
  "Login required", and the rest of the app continues on last-known state.

---

## 5. Instruments

### 5.1 Instrument master
- Upstox publishes a gzipped JSON of all instruments (NSE, BSE, NFO…). Downloaded once per
  day at startup into `data/instruments-YYYY-MM-DD.json.gz` and loaded into the
  `instruments` table.
- Fields used: `instrument_key`, `trading_symbol`, `exchange`, `segment`, `name`,
  `expiry`, `strike`, `instrument_type` (CE/PE/FUT/INDEX), `lot_size`, `tick_size`.

### 5.2 Resolution per index
For each index in `INDICES`:
1. **Spot**: the index instrument (`NSE_INDEX|Nifty 50`, `NSE_INDEX|Nifty Bank`).
2. **Futures**: nearest monthly future whose expiry ≥ today.
3. **Options expiry**: nearest expiry ≥ today among that index's options. NIFTY has
   weekly expiries; BANKNIFTY only monthly. The rule is the same ("nearest ≥ today"); the
   data decides. Same-day expiry is *included* (expiring contract traded all day).
4. **Strike set**: ATM ± `strike_window` strikes at that expiry, using the exchange's
   strike step inferred from the master (50 for NIFTY, 100 for BANKNIFTY).
5. **Expiry-day flag**: `is_expiry_day = (options_expiry == today)`.

### 5.3 ATM and re-centring
- `ATM = round(spot / step) * step`.
- `SubscriptionManager` holds the current window. When ATM moves ≥ `recenter_strikes`
  from the window centre, it subscribes the new strikes, unsubscribes those that fell out,
  requests a chain REST snapshot for the new strikes (so they have opening-OI baselines),
  and publishes `WindowChanged`.

### 5.4 Roll-over
- After market close on an expiry day, the next startup resolves the next expiry
  naturally. No intraday roll.

---

## 6. Market data feed

### 6.1 Provider interface

```python
class MarketDataProvider(Protocol):
    async def connect(self) -> None
    async def subscribe(self, keys: list[str]) -> None
    async def unsubscribe(self, keys: list[str]) -> None
    def ticks(self) -> AsyncIterator[Tick]
    async def close(self) -> None
    def health(self) -> FeedHealth
```

```python
@dataclass(frozen=True)
class Tick:
    key: str              # instrument_key
    ts: int               # exchange timestamp, epoch ms
    ltp: float
    volume: int | None    # cumulative day volume
    oi: int | None
    bid: float | None
    ask: float | None
    iv: float | None      # if the feed provides it
    delta: float | None   # if the feed provides it
    close_prev: float | None
    # order flow (Milestone S1)
    bid_qty, ask_qty, bid_qty5, ask_qty5, tbq, tsq: int | None
    atp: float | None; ltq: int | None
    # the feed's day candle, sent for MCX futures (§6.6)
    day_open, day_high, day_low: float | None
```

`FeedHealth = {state: connecting|connected|disconnected, last_tick_ts, reconnects,
subscribed, provider}`. Each provider also has a `name`.

### 6.2 Upstox provider
- Obtains a websocket authorisation URL via REST, connects, sends a binary subscribe
  message for the key list in `full` mode (LTP, depth, OI, Greeks where available).
- Messages are protobuf (`MarketDataFeed.proto`); decoded to `Tick` objects. Only fields
  that changed are populated; `Tick` consumers treat `None` as "unchanged".
- Reconnect with exponential backoff (1s → 30s cap), re-subscribe on reconnect, surface
  every disconnect as a `FeedHealthChanged` event.
- Rate and subscription limits are enforced client-side from configuration discovered in
  Milestone 1.

**Order-flow fields (Milestone S1).** From `marketFF` the provider also keeps the
quantity at the best bid and ask (`bid_qty`, `ask_qty`), the quantity summed over the five
book levels (`bid_qty5`, `ask_qty5`), total buy and sell quantity (`tbq`, `tsq`), the
exchange average traded price (`atp`) and the last traded quantity (`ltq`). They are
recorded with every tick so the order-flow trigger (Milestone S2) can be studied and
replayed; days recorded earlier read back as `None`. The synthetic provider generates the
same fields, with the books leaning the way its market is drifting.

**India VIX.** `NSE_INDEX|India VIX` is subscribed alongside the two indices as an
index-only key: its ticks are recorded and its latest price and previous close are kept,
but it has no candles, no futures and no chain. It feeds the index details view (§7.4).

### 6.3 Replay provider
- Reads `ticks` rows for a given date, emits them in timestamp order at `speed` ×
  real-time (or as fast as possible when `speed = 0`), setting the driven market clock
  from each tick. Used by tests, after-hours demos, and Milestone 6 fault injection: it can
  be told to drop (withhold) time ranges (`replay_drop`).
- With `replay_bullion`, the day's `bullion_ticks` are merged in by time and the bullion
  desk runs on them (§9a).

### 6.4 Tick bus and store
- `TickBus` is a synchronous fan-out: each `StampedTick` (tick plus ingest time) is handed
  to every subscriber in turn: the session (prices, tick store, candles), chain manager,
  order flow, outcome tracker, paper trades, and the bullion tracker and desk.
  Subscribers must not block.
- The tick store batches inserts (500 rows, and a flush twice a second) into `ticks`;
  bullion ticks go to `bullion_ticks` instead (§6.6). Nothing is recorded in replay.

### 6.5 Late start and backfill
On startup (or after login) when the market is already open:
1. Fetch today's 1-minute candles for spot and futures from Upstox intraday candle REST
   and seed the Candle Builder, so EMA/VWAP/supertrend have history.
2. Fetch the option-chain REST snapshot; use its OI as the *current* OI, and derive
   *opening* OI as `current_oi − oi_change_day` when the endpoint provides day change,
   otherwise treat the first observed value as opening and flag `oi_baseline=partial` in
   the evidence breakdown.
3. On every start, late or not: fetch one year of daily candles per index
   (`GET /v3/historical-candle/{key}/days/1/{to_date}/{from_date}`, `to_date` = the
   previous trading day) and keep the highest high and lowest low as the 52-week range
   before today (§7.4). One request per index per start. A failure is logged in
   `feed_events` and the 52-week fields stay empty; nothing else depends on them.

### 6.6 Bullion (Milestones E4, E6)
Gold and silver on their own tab, BULLION, beside the indices. Since E6 bullion has its
own trend bias, long/short signals on the near-month future and paper trades (§9a). It
still never feeds the index bias or signals, it never reaches the shared `CandleBuilder`
or the `ticks` table, and there is no real-order path for it.
- **Contracts.** Upstox has no spot price for gold or silver, so the prices are MCX
  futures of `GOLD` (₹ per 10 g) and `SILVER` (₹ per kg). Upstox's MCX instrument file
  (`.../exchange/MCX.json.gz`, public) is downloaded once a day to
  `data/mcx-instruments-YYYY-MM-DD.json.gz`. Records are matched on `segment = MCX_FO`,
  `instrument_type = FUT` and `underlying_symbol`, because `name` is `GOLD` for every gold
  contract, minis and petals included. The **near** contract is the nearest expiry strictly
  after today, so it rolls on expiry day, when the expiring one is in its delivery period.
  The **next** contract is the one after it. All four are subscribed.
- **Live, from the feed** (`full` mode), for the near contract:
  - last price and previous close (`cp`)
  - the day's open, high and low, from the `1d` row of `marketOHLC`; if that row is absent,
    the start quote widened by each price
  - average traded price, volume and open interest
  - best bid and ask with their quantities
  - total buy and sell quantity
  - for the next contract, its price only
- **Once at start:**
  - the full quote (`GET /v2/market-quote/quotes`): circuit limits, and the open, high, low
    and previous close shown before the first tick. Its `ohlc.close` is the live price, so
    the previous close is `last_price − net_change`; its `oi_day_high` and `oi_day_low` are
    0 for MCX and not used.
  - the contract's high and low over a year of daily candles to yesterday, the same request
    as the 52-week range in §6.5, widened by today; days with no volume are skipped, since
    an untraded future's early days carry placeholder prices (a gold contract showed
    ₹2,47,917 on one)
  - today's 1-minute candles from the intraday candle API
  - each of these fails soft: logged, the field left empty
- **Derived** (`market/bullion.py`, pure):
  - change and change % on the day
  - position in the day's range
  - bid-ask spread
  - buy/sell quantity ratio
  - calendar spread (next minus near, and as % of near)
  - **gold/silver ratio** = gold × 100 / silver, i.e. kilograms of silver one kilogram of
    gold buys
- **Chart.** Bullion has its own `CandleBuilder` (900 minutes; MCX runs 09:00–23:30),
  because the shared one drives the bias engine. The VWAP line is the running close ×
  volume from the first candle of the day.
- **Live feed only.** Loaded at start with the `upstox` provider, after the index backfill
  and before connecting. A failure leaves the tab out; it never stops the index feed.
  Synthetic has no bullion; replay has it only with `replay_bullion` (§9a).
- **Recorded apart.** Bullion ticks are never written to `ticks`: MCX trades until 23:30,
  and evening ticks there would stretch every NSE replay and drive its clock past the NSE
  close. Since E6 they go to their own table, `bullion_ticks`, and closed bullion candles
  to `candles_1m` under the MCX key (§9a).
- **Hours and liveness.** MCX keeps its own hours: `mcx_open`/`mcx_close` in settings
  (09:00 to 23:30; 23:55 while the US is on standard time, set by hand with the season) and
  `config/mcx-holidays.txt`, where a line with a time (`2026-12-25 17:00`) is a day with
  the morning shut and an evening session. `FeedSession.mcx_clock` is a second
  `MarketClock` on the same time source, so replay drives both. One socket carries both
  exchanges, but liveness is judged per exchange: index liveness (§14) counts NSE ticks
  only, so gold ticking never hides an index outage. Bullion is `live` when MCX is open
  and a bullion tick arrived within `bullion_live_max_tick_age_ms` (15 s); otherwise
  `stale`, `closed` or `holiday`. An MCX outage is logged to `feed_events`
  (`bullion_gap_start`/`bullion_gap_end`) and changes nothing else: no degraded mode, no
  effect on signals or paper trades.
- **API:**
  - `GET /api/bullion` (the snapshot) and `GET /api/bullion/{metal}/candles`
  - `bullion` (status and `since_ms`) in the health response and `health` frame. On the
    BULLION tab the banner follows it instead of the NSE session: no "Market closed" while
    MCX trades, "Bullion prices are not updating" when stale. Login and connection banners
    still come first, and an index outage is still shown there, without dimming bullion.
  - The top bar follows the tab too: on BULLION the market pill reads `MCX LIVE` /
    `MCX CLOSED` and the feed pill's tick age is the newest bullion tick. On any tab, a
    tick age turns amber or red only while that market is open; a closed market's
    silence is shown muted.
  - `bullion` and `bullion_candles` in `hello`
  - a `bullion` frame throttled like `tick`, and a `bullion_candle` frame on each close

### 6.7 News headlines (Milestone E10)

A quick check on what is moving the market. **Display only**: news is not an input to the
bias, signals or paper trades, and nothing about it is stored.

- **Source:** Upstox `GET /v2/news?category=instrument_keys&instrument_keys=…` with the
  daily login's Bearer token. Up to 30 keys a call; the last 7 days; paged
  (`page_number` 1–100, `page_size` 1–100). Each item has `heading`, `summary`,
  `thumbnail`, `article_link` and `published_time` (epoch ms), grouped by the key it is
  attached to. Tested on 16/11/2026: only `NSE_EQ` stock keys carry news; `NSE_INDEX`,
  `NSE_FO`, `MCX_FO` keys and `category=positions` return nothing, so there is no
  bullion news. Volume is low (about 25 items a week over 11 heavyweights), much of it
  market wraps, and one story is often attached to several stocks.
- **Which stocks:** `config/news-stocks.txt`, one `SYMBOL INSTRUMENT_KEY INDEX` per line,
  `#` comments, at most 30 (one call); the heaviest NIFTY and BANK NIFTY stocks, edited by
  hand (Upstox publishes no index weights). `INDEX` is `N` (NIFTY), `B` (BANK NIFTY) or
  `NB` (both) and only colours the stock's chip; it may be left out. A malformed file does
  not stop the app: the panel shows the error.
- **`market/news.py`:** `parse_news` (pure) flattens the per-key lists, merges items with
  the same `article_link` (else the same `heading`) into one headline carrying every
  symbol, and sorts newest first; items without a heading or a numeric time are skipped.
  `fetch_news` (in `feed/upstox.py` beside the other REST helpers) reads every page.
  `NewsService` is built in `build_state`, hung on `AppState.news`, and started and
  stopped in the lifespan. It is independent of `FeedSession`, so a login that has not
  started the feed still gets news, and it can never hold up the feed. Every
  `news.poll_seconds` (a parameter, §3.2; default 180, edited in the Config control) while
  `AuthService.token` is valid it fetches, and when the list or status changed publishes
  `NewsChanged` on the `EventBus`. `AuthChanged("valid")` makes it fetch at once;
  `ParametersChanged` makes it re-read the interval without fetching early.
- **Status:** `needs_login` (no valid token: always so on synthetic and replay),
  `loading` (token valid, first fetch pending), `ok`, `error`. A 401 calls
  `auth.mark_expired()`; any other failure (HTTP error, timeout) sets `error` and keeps
  the last good list; the next success clears it.
- **API:** `news` (`NewsOut`: status, error, fetched_at, items of `HeadlineOut`: heading,
  summary, link, published_ts, symbols; and `stock_indices`, each listed symbol's indices)
  in `hello`, and a `news` frame on change. No REST endpoint.

### 6.8 Macro data (Milestone E12)

The data behind the macro group of the bias (§8.6). Upstox has no dollar index (no DXY in
the NSE or MCX instrument files, checked 2026-11-18), so the dollar comes from NSE's
currency futures.

- **Contracts:** the near-month futures of USD/INR, EUR/INR, GBP/INR and JPY/INR (`NCD_FO`
  rows of the NSE file, `parse_currency_futures`) and MCX CRUDEOIL (`parse_commodities`),
  each by `resolve_commodity_months` (rolls on expiry day). Gold and silver are the
  bullion tracker's near contracts (§6.6), not subscribed twice.
- **`market/macro.py:MacroTracker`:** its own `CandleBuilder` and the latest tick time per
  contract. `build_view()` gives each indicator its 1-minute closes up to the minute being
  evaluated (the forming minute included) and whether its last tick is within
  `macro.max_age_seconds`. The dollar series is `dollar_index_proxy()` of the four
  currencies' closes, side by side per minute (`align_closes`, last close carried forward).
- **Side market:** `FeedSession.is_side_market()` treats every `MCX_FO|` and `NCD_FO|` key
  (and the trackers' keys) alike: never the index candle builder, never index liveness,
  recorded in `bullion_ticks` (currency trades to 17:00, crude to 23:30; `ticks` would
  stretch NSE replays).
- **Loading:** with the `upstox` provider, and in replay with `replay_bullion` (contracts
  from that day's cached files). Today's candles are backfilled at start so the window is
  full at once. Every step fails soft: the index feed always starts.
- **GIFT Nifty (Milestone E14):** not in the NSE or MCX files; Upstox lists it in its
  global instrument file (`global.json.gz`) as `GLOBAL_INDEX|SGX NIFTY` with a 120 s
  refresh, for the quote and candle APIs (the WebSocket is not documented for it, and it
  is not subscribed). There is no GIFT Bank Nifty. `market/gift.py:GiftNifty` fetches,
  once NSE has been open a minute, the previous NSE trading day's and today's 1-minute
  candles (`fetch_day_candles`, `fetch_intraday_candles`), retrying every 2 minutes until
  it has a reading, and stores GIFT's last close before the previous 15:30 and its last
  close before today's 09:15 in `gift_nifty` (migration 013), one row per day. Replay reads
  that row whatever `replay_bullion` says; `tools/score.py` copies it with the ticks. On
  synthetic there is none.

---

## 7. Market state

### 7.1 Candle builder
- Per instrument, aggregates ticks into 1-minute OHLCV candles keyed by
  `floor(ts / 60_000)`. Volume per candle is the delta of cumulative day volume.
- On minute boundary (driven by the exchange timestamp, not wall clock, with a 2 s
  wall-clock fallback when ticks are sparse), the candle is closed, persisted to
  `candles_1m`, and handed to the builder's close listeners (the bias engine and the
  session's candle listeners).
- Gaps (no ticks in a minute) produce a carry-forward candle (O=H=L=C=prev close, V=0)
  flagged `synthetic=True`, so indicator windows stay aligned.
- VWAP is maintained on the futures stream from session open: `Σ(price×vol) / Σvol`.
- **Net volume (Milestone E8).** Upstox does not say which side started a trade, so each
  tick's volume change is signed (`trade_side`): at or above the ask as it stood before the
  tick is a buy; at or below the bid, a sell; in between, the **tick rule** (up from the
  last trade is a buy, down a sell, unchanged keeps the last side). Each candle keeps
  `buy_volume` and `sell_volume`; `None` where there is no side information (an index has no
  volume; backfilled minutes come from the candle API without trades). On a recorded day
  the quote rule alone classified 85 % of NIFTY and 90 % of BANK NIFTY futures volume; the
  tick rule covers the rest. A volume jump after more than 30 s with no tick
  (`SIDE_GAP_MS`, E13) is every trade the gap hid, not one trade, so it is counted in the
  volume but not signed. For the indices it is display only; the bullion bias reads it
  from E13 (`net_volume`, §9a). The order-flow score (§8.5) signs trades its own way over
  seconds and is unchanged.

### 7.2 Chain state
Per index, in memory:

```python
class StrikeRow:
    strike: float
    ce: LegState; pe: LegState    # ltp, chg, oi, oi_open, oi_prev_min, iv, delta, volume
class ChainState:
    index: str; expiry: date; atm: float; rows: dict[float, StrikeRow]
    history: deque[ChainSnapshotMinute]   # last 60 minutes of (pcr, max_pain, atm, ...)
```

Derived values, recomputed on every tick that changes OI or LTP (cheap, ≤ 21 rows):
- **PCR** = `Σ PE OI / Σ CE OI` over ATM ± `pcr_strike_range`.
- **OI change since open** and **since previous minute**, per leg.
- **Max pain** = strike minimising total payout to option buyers across the window.
- **Build-up classification** per leg per minute, from sign of Δprice and ΔOI:
  long build-up (+,+), short build-up (−,+), short covering (+,−), long unwinding (−,−).

A `ChainSnapshotMinute` is appended on each minute close and persisted to
`chain_minutes` (one row per strike per minute) for replay and tuning.

### 7.3 IV and Greeks
IV and delta are taken from the feed where it sends them. Delta is needed for expiry-day
targets and for live levels; when the feed has none it is computed with Black-Scholes
(`indicators/greeks.py:bs_delta`) from spot, strike, time to the 15:30 close on expiry
day, the option's IV from the feed (15 % if unknown) and `risk_free_rate` *(default
6.5 %)*. IV itself is never solved for; the IV-change indicator uses the feed's IV only.

### 7.4 Index day statistics

One `IndexStats` per index, for the details view. It is display-only: no indicator, signal
or paper trade reads it.

```python
class IndexStats:
    index: str
    day_open, day_high, day_low: float | None
    range_pos: float | None        # 0 at the day's low, 1 at the day's high
    prev_close: float | None
    change, change_pct: float | None
    high_52w, low_52w: float | None
    fut_premium: float | None      # futures LTP − spot LTP
    vix, vix_change_pct: float | None
    updated_ts: int | None
    sectors: tuple[SectorQuote, ...]   # Milestone E11

class SectorQuote:
    name: str                      # Upstox NSE_INDEX name: "Nifty Fin Service"
    label: str                     # without "Nifty ": "Fin Service"
    ltp, prev_close: float | None
    change, change_pct: float | None
```

| Value | Source |
|---|---|
| Day open / high / low | today's closed spot candles plus the candle being formed; complete from 09:15 after a late start because of the candle backfill (§6.5) |
| Range position | `(spot − day_low) / (day_high − day_low)`; empty while high equals low |
| Previous close, change, change % | previous close from the feed (`cp` on the spot tick); change = spot − previous close |
| 52-week high / low | the range before today from §6.5 step 3, widened by today's high/low on every update, so a new extreme shows the moment it happens |
| Futures premium | latest futures LTP − latest spot LTP |
| India VIX and its change % | the VIX key's LTP and previous close (§6.2) |
| Sectors (E11) | for each name in `sector_indices[index]`, in that order, the `NSE_INDEX|<name>` key's LTP and previous close; change = LTP − previous close |

Any value without a source is `None` and shown as "—". On the synthetic feed that is the
52-week range, previous close, VIX and the sectors; on replay it is the 52-week range, and previous
close and VIX for days recorded before E1 (previous close is stored with ticks from E1 on,
once per instrument whenever it changes).

Recomputed on spot, futures and VIX ticks; cheap enough not to cache beyond the latest
value.

**Sector indices (Milestone E11).** `market_wide_keys()` subscribes India VIX and every
configured sector key once (Fin Service and PSU Bank serve both indices), on every feed but
the synthetic one. Their ticks are recorded in `ticks` like VIX, so a replay brings them
back, and they count toward NSE liveness as VIX does; nothing else reads them (the candle
builder takes spot and futures keys only). The default names were checked against the
Upstox instrument file; a wrong name is not rejected, it just never ticks and shows "—".

---

## 8. Indicators

All indicators are pure functions `f(inputs) -> IndicatorResult`:

```python
@dataclass(frozen=True)
class IndicatorResult:
    name: str
    group: Literal["trend", "oi", "premium", "flow", "macro"]
    score: float            # clamp to [-1, +1]; +bullish / −bearish
    value: dict[str, float] # raw numbers shown in the evidence table
    note: str               # one-line human reason, e.g. "EMA9 above EMA21 by 0.12%"
    quality: Literal["ok", "warming", "partial", "info"]
```

`quality != ok` indicators are shown greyed and contribute 0 until they have enough data.
`info` is shown for context and never scored (silver in the index macro group; GIFT Nifty
outside its window). `flow` is weighted only in the bullion bias (§9a); `macro` in both.

### 8.1 Price trend group (weight 0.40, equal split within group)

| Indicator | Inputs | Score |
|---|---|---|
| `ema_cross` | spot 1-min closes | `tanh(k · (EMA9 − EMA21) / EMA21 · 100)` with *k = 8*; sign gives direction, magnitude saturates near ±0.25 % separation |
| `vwap_position` | futures close, VWAP | `clamp((close − VWAP) / VWAP · 100 / 0.3, −1, 1)` — ±0.3 % from VWAP is full strength |
| `supertrend` | spot OHLC | +1 if close above supertrend line, −1 if below, scaled by `min(1, bars_since_flip / 3)` so a fresh flip starts at 0.33 |

### 8.2 OI structure group (weight 0.35, equal split)

| Indicator | Inputs | Score |
|---|---|---|
| `pcr` | ChainState | `clamp((PCR − 1.0) / 0.5, −1, 1)` — PCR 1.5 is fully bullish (put writers confident), 0.5 fully bearish |
| `oi_change_atm` | ATM ± 2 build-up classes, weighted by ΔOI size | The premium's direction decides the side, the OI moved is the weight. Call long build-up and short covering (premium up) → bullish; call short build-up and long unwinding (premium down) → bearish; puts the mirror image *(owner's decision, 2026-11-14; before that any OI rise on a call counted bearish and on a put bullish, whatever the premium did)*. Score = `(bull_oi − bear_oi) / (bull_oi + bear_oi)` over the window |
| `max_pain_drift` | ChainState history | `clamp((max_pain_now − max_pain_15m_ago) / (2 · step), −1, 1)` — max pain migrating up is bullish |

On expiry day the whole group's weight is halved and the shortfall is redistributed
pro-rata to the other two groups; each result carries `note += " (expiry day)"`.

### 8.3 Premium behaviour group (weight 0.25, equal split)

| Indicator | Inputs | Score |
|---|---|---|
| `premium_momentum` | ATM CE and PE LTP, 5-min ROC | `clamp((roc_ce − roc_pe) / 20, −1, 1)` — a 20-point spread in % ROC is full strength |
| `iv_change` | ATM IV vs 15 min ago, with spot direction | rising IV with rising spot → bullish continuation (+); rising IV with falling spot → bearish (−); falling IV damps toward 0. Score = `sign(Δspot) · clamp(ΔIV / 2, 0, 1)` |
| `premium_confirmation` | Δspot over 5 min, ΔCE, ΔPE | if spot up and CE gained more than PE lost (in %), +1 scaled; disagreement (spot up, CE flat/down) → −0.5 "divergence" |

### 8.4 Aggregation

```
group_score = mean(score of indicators with quality == ok in group)   # 0 if none
bias        = Σ weight_g · group_score_g                               # ∈ [-1, 1]
strength    = round(|bias| · 100)
label       = Bullish if bias ≥ neutral_band, Bearish if bias ≤ −neutral_band, else Neutral
```

Groups since E12: trend, OI, premium and macro (§8.6); E13 adds `flow`, which only the
bullion bias weighs (§9a; the index reads order flow at the trigger, §8.5) and the index
gives 0. `weights.macro` is carved out
first and the other three keep their proportions in the rest
(`effective_group_weights`): 0.36 / 0.315 / 0.225 / 0.10 by default. On expiry day the
OI cut is spread over trend, premium and macro in proportion. **If no macro indicator is
`ok`** (no live feed, the currency market shut after 17:00, a window still filling), the
macro share goes back to the other groups in proportion, so the bias is exactly the
three-group one. An `info` reading (silver) is shown with weight 0. The groups that give
their share back when idle are an argument of `aggregate()`: macro for the indices
(`INDEX_IDLE`), OI, flow and macro for bullion (`BULLION_IDLE`).

**Factor switches (Milestones E15, E16).** Asked for on 2026-11-19: each factor of each
index's and metal's bias can be switched off; every factor is on by default. Since E16 the
switches are parameters: `factors.nifty`, `factors.banknifty`, `factors.gold` and
`factors.silver`, one `"on"`/`"off"` value per factor (`IndexFactors`, `NiftyFactors` with
`gift_nifty`, `BullionFactors`; a test keeps the names equal to what the engines emit).
They are flipped only in the Config drawer's **Factors** tab (§13.2), and each flip is saved at once
as its own version tagged `Factor NIFTY.pcr: off` (`ParameterService.set_factor`,
`PUT /api/parameters/factors/{scope}/{name}` `{enabled}`; no version when already so). The
typed editor does not list them (`describe()` skips `factors`) and a typed save keeps the
switches in force. The Evidence panel shows each factor's switch read only. Each engine
reads `p.factors.off_for(index)` at its evaluation and passes it to `aggregate()` as `off`:
such a factor is still worked out and shown, but has weight and contribution 0 and is left
out of its group's score, so the group's other live members share its weight. A group whose
every member is off gives its share back to the others in proportion, whatever
`idle_groups` says. Each contribution carries `enabled`, stored in every breakdown. Like
any parameter, a flip applies from the next evaluation, never mid-minute; signals record it
through `config_version`, Revert brings switches back, and `tools/score.py --params`
replays with a trial file's switches. (E15 kept switches outside the config in
`app_state`; migration 014 drops that, starting every factor on.)

A `BiasComputed(index, ts, bias, label, strength, breakdown)` event is published every
minute close and persisted to `bias_minutes`. `breakdown` is the list of
`IndicatorResult` plus the effective group weights.

### 8.5 Order flow (Milestone S2)

Not part of the bias. A separate, faster reading per index, from the order-flow fields of
the feed (§6.2), of who is leaning on the book and who is paying up. Three parts, each
from −1 (selling) to +1 (buying):

- **Futures book:** `(bid − ask) / (bid + ask)` on the five-level quantities and the same
  on total buy and sell quantity, averaged; then the mean of the readings seen in the
  window.
- **Futures trades:** each rise in day volume is a trade, counted as buying if the price
  is at or above the ask that stood before it, selling if at or below the bid, and
  neither in between; net signed volume ÷ total volume in the window.
- **Options:** (flow in the ATM call − flow in the ATM put) ÷ 2, where a leg's flow is the
  mean of its book and trades readings. Needs both legs; follows the current ATM strike.

The score is the weighted mean (`w_fut_book`, `w_fut_trades`, `w_options`) of the parts
that have data in the last `window_seconds`. A part with no data is left out, never
counted as zero; with no part the score is unknown. A `FlowReading` is produced about once
a second per index, timed by tick timestamps so replay reads the same as live. Days
recorded before the order-flow fields still have bid, ask and volume, so they give a score
from the trades readings alone, without either book reading.

*(my call: the window, the weights and the 0.25 trigger are starting values with no
evidence behind them yet; the shadow scorecard is how they get tuned.)*

### 8.6 Macro group (Milestone E12)

Asked for on 2026-11-18: the dollar, crude and bullion trends in the signal, live with a
small weight (`weights.macro` 0.10), and in the bullion bias too. Pure functions in
`indicators/macro.py` over the data of §6.8.

Each reading is the instrument's move over `macro.window_minutes` (30) of 1-minute
closes: `score = sign · clamp(change% / full%)`. With no price, too few closes or a price
older than `macro.max_age_seconds` (180) it is `warming` and carries no weight.

| Indicator | Instrument | Index sign | Bullion sign | Full % |
|---|---|---|---|---|
| `dollar_index` | dollar-index proxy | − (strong dollar: foreign outflows) | − (gold falls with a strong dollar) | `dollar_full_pct` 0.15 |
| `usd_inr` | USD/INR future | − (weak rupee) | + (MCX price = world price × USD/INR) | `usdinr_full_pct` 0.10 |
| `crude` | MCX CRUDEOIL | − (import bill, inflation) | — | `crude_full_pct` 0.80 |
| `gold` | MCX GOLD | − (money seeking safety) | — | `gold_full_pct` 0.40 |
| `silver` | MCX SILVER | shown, never scored (`info`) | — | — |

**Dollar-index proxy** (`dollar_index_proxy`): with `EURUSD = EURINR / USDINR`,
`GBPUSD = GBPINR / USDINR` and `USDJPY = USDINR / (JPYINR / 100)` (JPY/INR is quoted per
100 yen), proxy = `EURUSD^−0.693 · USDJPY^0.164 · GBPUSD^−0.143`: the real DXY's euro,
yen and pound weights (0.576, 0.136, 0.119, 83 % of it) renormalised; the Canadian
dollar, krona and franc are not traded on NSE. Only its % change is used, so its level
and the futures' forward premium do not matter. A move of the rupee alone leaves it
unchanged; that is what `usd_inr` reads.

**GIFT Nifty gap (Milestone E14, NIFTY only).** Asked for on 2026-11-19. During NSE hours
GIFT Nifty is a 2-minute-late copy of the NIFTY future the bias already reads, so it is
used only for what it knows while NSE is shut: the overnight move,
`move% = preopen / ref − 1` (both GIFT's own prices, §6.8, so its premium over spot
cancels). `indicators/gift.py:gift_gap` scores it
`dir · clamp(move% / gift_full_pct) · (1 − m / gift_fade_minutes)`, where `m` is the
minutes since the open at the close of the minute evaluated and `dir` is +1 for
`gift_direction = "follow"`, −1 for `"fade"`. From `m ≥ gift_fade_minutes` (and before the
open) it is `info`; without a reading it is `warming`. Defaults: 0.50 %, 30 minutes,
follow. It is one more macro member, so it shares the group's weight equally with the live
ones; alone (replay without `replay_bullion`) it carries the whole group.

Every reading is in the bias breakdown, so each bias minute and each signal keeps its
macro evidence; `signals.config_version` separates signals before and after.

*(my call: the window, the full-strength moves and the signs are starting values from how
these markets usually relate to Indian equities, not from TradeDisha's own data. Macro
ticks are recorded from E12 on, so `tools/score.py` can tune them once there are weeks of
them.)*

---

## 9. Signal engine

### 9.1 State machine per index

```
          |bias| ≥ entry_threshold ∧ no active ∧ within hours ∧ feed live
 IDLE ───────────────────────────────────────────────────────────────► ACTIVE
   ▲                                                                      │
   │  lapsed (TTL) │ reversed (bias sign flips or |bias| < neutral_band)  │ traded
   └──────────────────────────────────────────────────────────────────────┘
```

- Evaluated once per minute close. The only gates are: bias beyond threshold, no signal
  currently active on that index, within signal hours, feed live. **Open paper trades
  never gate a signal, in either direction** (Anuj's decision).
- `ACTIVE → traded` when a paper trade is opened from it; the signal is kept as the
  trade's origin but is no longer active, so if bias is still beyond threshold at the next
  minute close a fresh signal fires at the then-current ATM and price. Likewise after a
  lapse. The trader is never without a current signal while bias supports one.
- `rearm_hysteresis` (default 0 = off): if set > 0, a new signal in the *same* direction as
  the one that just ended requires `|bias|` to fall below `entry_threshold −
  rearm_hysteresis` and re-cross first. Kept as a knob for tuning; off by default.
- Within hours: `MARKET_OPEN ≤ now < last_signal_time` (`last_signal_time_expiry` on
  expiry day).
- Feed live: feed health `connected` and last tick age < 5 s *(my call)*; otherwise the
  engine still computes bias (greyed) but fires nothing.
- Each evaluation records a `Gate` per index (fired or the reason it did not:
  `below_threshold`, `active_exists`, `rearm`, `outside_hours`, `feed_down`, `no_price`; in
  trigger mode also `no_setup`, `flow_not_confirmed`, `spread_wide`; for bullion also
  `disabled`) so the signal card can explain an empty state.

### 9.2 Signal content

```python
class Signal:                       # engine/signals.py; table `signals`
    id, index                       # index is NIFTY / BANKNIFTY, or GOLD / SILVER (§9a)
    minute_ts, ts_fired             # the minute evaluated; the moment it fired
    direction: BUY_CE | BUY_PE | BUY_FUT | SELL_FUT
    instrument_key, trading_symbol, strike, expiry
    lot_size                        # bullion: rupees per point per lot
    entry_price                     # option LTP (or ask, trigger rule); future's LTP (bullion)
    target_price, stop_price        # as fired; never changed
    target_basis                    # "pct" | "points"
    target_points, stop_points, delta_used   # expiry day
    bias, strength, breakdown_json
    expires_at                      # ts_fired + signal_ttl_seconds
    status: active | traded | lapsed | reversed; status_ts
    entry_ask, spread_pct           # the quote at firing
    entry_mode: minute_close | trigger; shadow: bool; flow_score
    config_version                  # parameters in force when it fired
```

The API adds `outcome` (§9.5) and, while the signal is active, `live` = {ltp, target,
stop} (§9.3).

### 9.3 Target and stop
- **Normal day**: `target = entry × (1 + target_pct/100)`, `stop = entry × (1 + stop_pct/100)`.
- **Expiry day**: points → premium via delta at fire time:
  `target = entry + |delta| × target_points`, `stop = entry − |delta| × stop_points`,
  floored at `0.05`. `delta` from feed or computed (§7.3). Both the point and premium
  values are stored and shown.
- **Live levels (Milestone E7).** The fired levels are stored and never change. While a
  signal is active, `SignalEngine.live()` / `BullionSignalEngine.live()` apply the same rule
  to the price now (`signals.py:rescale_levels`): a percentage signal keeps its target/entry
  and stop/entry ratios (so a config change after it fired does not move it); an
  expiry-day signal re-applies its index points through the option's **current** delta
  (from the feed, else Black-Scholes). `SignalOut.live` = {ltp, target, stop}, `None` once
  the signal has ended; a `signal_live` frame carries every active signal once a second. The
  signal card shows the Fired and Live rows side by side.

### 9.4 Interaction with open paper trades
Open trades never block signals. When a signal is shown on an index with open trades,
the signal card lists them prominently (option, entry, current P&L, time open, and
"opposite side" when they disagree with the signal). The frontend takes them from the open
trades it already holds; the signal itself carries nothing about them.

Independently of signals, on every `BiasComputed` the `PaperTradeManager` sets
`warning = "bias_reversed"` on each open trade whose direction opposes the new label
(CE trade with `Bearish` label, PE trade with `Bullish` label) and clears the warning when
the label no longer opposes it (for bullion: a long future while Bearish, a short while
Bullish). Each change goes to the trade listeners and out as a `paper_trade` frame. The
warning is informational; it never closes a trade.

### 9.5 Outcomes and the scorecard (Milestone S1)

Every signal is scored by what its option did next, whether or not it was paper-traded and
whatever became of it (lapsed, reversed, traded). This is the yardstick for any change to
the signal rules.

- The `OutcomeTracker` follows the signal's option from `ts_fired` to the earlier of
  `ts_fired + outcome_horizon_minutes` and the square-off time.
- **Result:** `target` or `stop`, whichever price was touched first; `neither` if the
  horizon ends untouched; `open` until then. Prices are last traded prices against the
  signal's own target and stop.
- The best and worst option prices keep being followed to the end of the horizon even
  after the result is known, so a stop hit just before a run to the target shows as that.
- Also kept: the option price 1, 5 and 15 minutes after firing; the spot at firing; the
  spot move over the 10 minutes before firing and the best spot move after it, both
  signed in the signal's direction.
- **Lateness** (`late_share`) = move before ÷ (move before + best move after), counting
  only favourable moves: 0 means the signal fired at the start of the move, 1 at its end.
- Each signal also stores the best ask and the bid-ask spread (% of mid) at firing.
- Time comes from tick timestamps, never the wall clock, so a replayed day scores the same
  at any speed. Unfinished outcomes are reloaded after a restart.
- A result or a closed horizon re-sends the signal on the websocket with its outcome.

The **scorecard** sums a date range: signals, how many are scored, the share that reached
target first, stop first or neither, the average best and worst move (% of entry), and the
average lateness; one row for everything and one per index.

`uv run python -m tradedisha.tools.score [--days D ...] [--db FILE] [--params FILE]` replays
recorded days at full speed, each in a scratch database, with the given parameter file, and
prints the scorecard. The recorded database (`--db`, default `TRADEDISHA_DB_PATH`) is opened
read-only. Running it with the current file and with a trial file is how a parameter change
is judged.

The scorecard keeps each entry rule apart (§9.6): rows carry the rule and whether it was
running in shadow, live rules first.

### 9.6 Entry rules and the shadow engine (Milestone S2)

`signal.entry_mode` picks the live rule:

- **`minute_close`** (default): §9.1 as it stands.
- **`trigger`** (setup, then trigger):
  - *Setup.* At a minute close, `|bias| ≥ setup_threshold` sets up that direction; below
    it the setup is dropped. `setup_threshold` must lie above `neutral_band` and no higher
    than `entry_threshold`.
  - *Trigger.* On each flow reading while a setup stands and no signal is active: the flow
    score must agree with the setup's direction at `trigger_score` or beyond,
    continuously for `hold_seconds`; a reading that fails restarts the count. Then the
    shared gates apply (re-arm, signal hours, feed live), and the option must have a
    two-sided quote no wider than `max_spread_pct` of its mid price.
  - *Signal.* Entry is the option's ask, not the last traded price; target and stop are
    worked from it as in §9.3. The signal carries the bias and breakdown of the minute
    that set it up, the flow score, and `entry_mode = trigger`.
  - One active signal per index, TTL, reversal and `traded` behave as in §9.1.
  - Gate reasons added: `no_setup`, `flow_not_confirmed`, `spread_wide`.

**Shadow engine.** A second `SignalEngine` always runs the rule that is not live, on the
same bias and flow. Its signals are stored with `shadow = 1` and scored (§9.5), sent to
the screen for the "Signals today" list only, never become the active signal, and cannot
be paper-traded (409). Changing `entry_mode` and reloading swaps which rule is live from
the next evaluation; the other carries on in shadow, so the comparison never stops.

---

### 9a. Bullion signals (Milestone E6)

GOLD and SILVER MCX near-month futures, run by `engine/bullion_desk.py:BullionDesk`
(bias -> signals -> paper trades) on the MCX clock and bullion liveness (§6.6).

- **Evidence.** There is no option chain for bullion. The bias has four groups, all read
  from the near future up to the minute being worked out (`indicators/futures.py`,
  Milestone E13, except trend):
  - *trend*: EMA cross, VWAP position and supertrend over the closed 1-minute candles;
  - *oi*: `futures_oi`, the price change against the OI change over
    `oi_window_minutes`. Build-up (OI up) counts fully in the price's direction, short
    covering and long unwinding (OI down) by `oi_unwind_factor`; a flat price reads 0. It
    warms across a feed gap: the reading compared against must be within 5 minutes of the
    window's start;
  - *flow*: `net_volume`, the buyer- less seller-initiated share of the signed volume over
    `flow_window_minutes` candles, and `book_imbalance`, the book's lean (total and
    five-level quantities) against its own average over `flow_book_minutes` readings,
    because MCX books lean one way for hours;
  - *macro*: (E12) `dollar_index` and `usd_inr` with the bullion signs of §8.6, and (E13)
    `peer_metal`, the other metal's trend (the mean of its `ok` trend votes).

  OI and book readings come from `BullionTracker.minute_book()`: the near contract as it
  stood at the end of each minute (its last tick), kept 900 minutes. Weights from
  `bullion_weights()`: OI `oi_weight` (0.15), flow `flow_weight` (0.15), macro
  `macro_weight` (0.10), trend the rest (0.60). A group with no `ok` reading gives its
  share to the live ones (`BULLION_IDLE`), so at start, before the new votes warm up,
  the bias is trend alone. Indicator periods come from `trend`; thresholds from the
  `bullion` section. Stored in `bias_minutes` under GOLD / SILVER and sent in the `bias`
  frame.
- **Evaluation offset.** A bullion minute is worked out `bullion.eval_offset_seconds`
  (default 20) after it closes, not at the close, so it never competes with the index
  engines; the index "minute close -> signal" budget (§14a) is untouched. A close queues the
  minute with its due time; due minutes run on each bullion tick and in housekeeping, on
  the market clock, so replay times them as live did. The lag is the latency hop
  `bullion_eval_lag`. A changed offset applies from the next minute.
- **Rule: minute close only** (no trigger, flow or shadow). |bias| >= `entry_threshold`
  fires `BUY_FUT` (bias > 0) or `SELL_FUT` at the future's latest price; target and stop are
  `target_pct` / `stop_pct` of that price in and against the signal's favour. One active
  signal per metal; TTL lapse, reversal (sign flip or inside the neutral band) and re-arm
  as §9.1.
- **Gates**, in order: `disabled` (`bullion.signals = off`), `below_threshold`,
  `active_exists`, `rearm`, `outside_hours` (MCX open and `first_signal_time` <= t <
  `last_signal_time`, 09:15–22:45 by default), `event_pause` (a US data release is near,
  below), `feed_down` (bullion status not `live`), `no_price`.
- **US data-release pause (Milestone E18).** CPI, payrolls and similar releases move gold
  and silver sharply, so a 1-minute trend signal around one is mostly noise. The releases
  are hand-kept in `config/us-events.txt` (`YYYY-MM-DD HH:MM label`, IST, read at start;
  `us_events_file`). From `bullion.event_pause_before_minutes` (15) before a release to
  `bullion.event_pause_after_minutes` (15) after it, `[release − before, release + after)`
  on the MCX clock, no bullion signal fires (gate `event_pause`); both 0 turn it off. Two
  switches set what else stops: `bullion.event_end_waiting = on` ends a signal still
  waiting when the window opens (`lapsed`, at the next evaluation or housekeeping pass),
  and `bullion.event_block_trades = on` refuses opening a bullion paper trade in the window
  (409, "paused around US data: CPI 19:00"). Both are off by default. Open trades are never
  touched. A missing file means no pause; a malformed one is logged and bullion runs
  without a pause (the load fails soft). The index engines never read it.
- **Stored** in `signals`: `index` is the metal, `strike` 0, `expiry` the future's, and
  `lot_size` the rupees per point per lot (the MCX file's `qty_multiplier`: GOLD 100,
  SILVER 30). Bullion signals skip the outcome yardstick and the scorecard (they score NSE
  spot moves).
- **Recording and replay.** Bullion ticks go to `bullion_ticks` (migration 011; the `ticks`
  columns plus the feed's day candle); closed bullion candles to `candles_1m` under the MCX
  key. `TRADEDISHA_REPLAY_BULLION=true` merges that day's bullion ticks into the replay and
  loads the day's contracts from the cached MCX file (no network).

---

## 10. Paper trading

### 10.1 Lifecycle

```
POST /paper-trades {signal_id}
  → validate signal is ACTIVE (and not shadow), its market open (NSE, or MCX for
    bullion), before its square-off time, not in a US-release pause when
    `bullion.event_block_trades` is on (§9a), its feed live (else 409 with reason)
  → open at current LTP of signal.instrument_key (not signal.entry_price)
  → slippage = fill − signal.entry_price
  → quantity = lot_size × lots (bullion: point value × bullion.lots)
  → the paper bank blocks the trade's money, or refuses (409) if it cannot (§10.5)
  → status OPEN; target/stop = the signal's live levels at the fill price (§9.3), so the
    trade gets what the card's Live row showed; signal_entry keeps the fired entry
```

No cap on concurrent open paper trades per index or direction *(my call, follows from
"always allow")*. The paper bank (§10.5) is the only limit: a trade it cannot fund is
refused with a 409, and the signal stays active.

On every tick for an open trade's instrument (for a short future, `SELL_FUT`, the
comparisons are mirrored: the target is below the entry):
- `ltp ≥ target` → close `TARGET`
- `ltp ≤ stop`   → close `STOP`
- Timer: at `square_off_time` → close `SQUARE_OFF` (bullion: `bullion.square_off_time`,
  23:00, on the MCX clock)
- `POST /paper-trades/{id}/close` → close `MANUAL` at current LTP (409 if feed not live)

Exit fill uses the LTP that triggered the exit (no simulated slippage on exit in v1).

**Fill quality.** Every exit records `exit_fill_quality`:

| Value | When |
|---|---|
| `live` | exit triggered by a tick while the feed was healthy |
| `after_gap` | the feed was down while the trade was open and the exit was triggered by the first tick after it resumed (price may have gapped past target/stop) |
| `stale` | square-off fired while the feed was down; fill is the last LTP the app saw, with its age recorded in `exit_price_age_ms` |

While the feed is down, target/stop are not evaluated (no prices). On the first tick after
resume, all open trades on that instrument are evaluated against it. The square-off timer
fires regardless of feed state. Entry always requires a live feed, so there is no entry
fill quality. The journal shows a badge for anything other than `live`.

### 10.2 P&L
```
gross = side × (exit − entry) × quantity        side = −1 for SELL_FUT, else +1
net   = gross − cost
cost  = cost_per_trade × lots                                   index options
cost  = cost_fixed_per_lot × lots
        + cost_pct_of_value / 100 × entry × quantity × 2        bullion futures
pct   = side × (exit − entry) / entry × 100
```
Hit = `net > 0`. Bullion's cost has a part that scales with value because a GOLD lot is
worth over a crore. Each market has its own `PaperTradeManager` (`PaperRules`: clock,
square-off, lots, cost) and restores only its own open trades after a restart; the API
sends an open or a close to the manager that owns the signal or trade.

### 10.3 Journal stats
Overall (index options only), per index, and, when there are bullion trades, a `bullion`
total and per metal: trades, hits, hit rate, average win (net), average loss (net),
net total, gross total, average duration, breakdown by exit reason, count of non-`live`
fills. Computed on request from `paper_trades`; small enough not to cache.

### 10.4 Tick pruning
`POST /data/prune-ticks {until_date}` deletes rows from `ticks` and `bullion_ticks` with
`ts < start of (until_date + 1 day) IST`, so the chosen date is included (Anuj's decision).
Nothing else is deleted; `candles_1m`, `chain_minutes`, `bias_minutes`, `signals`, and
`paper_trades` are untouched, so replay from candles remains possible. The call first
returns a preview (`GET /data/usage?until_date=`: day count, row count, estimated MB, both
tables together) and the UI requires confirmation. Deletion runs in batches of 50 k rows,
yielding to the event loop between batches so the feed keeps flowing, followed by
`PRAGMA incremental_vacuum`. Pruning the
current day while the feed is live is allowed; the tick store simply continues appending.
A `feed_events` row (`ticks_pruned`, with the date and row count) is written.

### 10.5 Paper bank
A fake bank account funds paper trades (Milestone E17). There is one account for every
market: NIFTY, BANK NIFTY, GOLD and SILVER draw on the same money. Nothing is ever deleted.

```
blocked   = entry × quantity + cost                                index option (premium paid)
blocked   = margin_pct(metal) / 100 × entry × quantity + cost      bullion future
balance   = opening balance + Σ net of every closed trade the bank funded
held      = Σ blocked of open trades
available = balance − held
```

- **Entry.** After the usual checks (§10.1), a trade opens only if `blocked ≤ available`;
  otherwise 409 `not enough money in the paper bank: needs ₹X, ₹Y available`. The signal is
  not marked traded, so it can still be taken once money frees up. The trade stores
  `blocked` and `banked = 1`.
- **Exit.** Closing releases the block and settles net P&L into the balance: profit is
  deposited, loss deducted, cost always deducted. A futures loss can exceed the margin it
  blocked, so the balance can go negative; every new trade is then refused.
- **Parameters.** `bank.opening_balance` (default ₹25 lakh), `bullion.gold_margin_pct` (10)
  and `bullion.silver_margin_pct` (12), edited in Config → Parameters.
- **Deposits and withdrawals.** The opening balance is the cash put in. Its first read
  records an `OPEN` row in `bank_ledger`. When the parameter changes, the difference is
  recorded as a `DEPOSIT` (new amount bigger) or a `WITHDRAW` (smaller), and the balance
  moves by exactly that amount. P&L made so far keeps counting, and open trades are
  untouched. Each save is recorded at once, because the `bank` frame pushed on a
  parameters change reads the bank. An edit made while the app was down is recorded on
  the next read. Saving the same amount moves no cash. A withdrawal is not capped by the
  free money: it can leave available below zero, and then new trades are refused until
  trades close.
- **Derived, not stored.** No running balance is kept: each read sums the funded trades
  in `paper_trades` (`banked = 1`). Trades from before E17 were not funded and never
  count.
- **API.** `GET /api/bank` → opening balance, when the bank opened, deposited, withdrawn,
  realised, balance, blocked, available, open trades and the ledger (oldest first). The
  same object is in `hello` (`bank`) and in a `bank` frame after any paper-trade change
  and after a parameters change. The page shows it as a strip above the open trades and
  at the top of the journal, with unrealised P&L (the open trades' live net) beside it.
  The journal also lists the ledger: date, time, kind, amount and the cash in after it.
  Each open trade shows what it blocks.

---

## 11. Persistence (SQLite)

One shared `sqlite3` connection in autocommit mode with WAL; tick inserts are batched. All
timestamps epoch ms UTC. The schema is plain numbered SQL files in `store/migrations/`,
applied in order at startup and tracked by `PRAGMA user_version`.

| Table | Key columns | Purpose |
|---|---|---|
| `sessions` | id, token, obtained_at, expires_at | daily auth |
| `instruments` | instrument_key, trading_symbol, exchange, segment, name, instrument_type, expiry, strike, lot_size, tick_size, loaded_on (key: instrument_key, loaded_on) | daily master subset |
| `ticks` | key, ts, ltp, volume, oi, bid, ask, iv, delta, close_prev, bid_qty, ask_qty, bid_qty5, ask_qty5, tbq, tsq, atp, ltq | raw NSE feed, replay source |
| `bullion_ticks` | the `ticks` columns plus day_open, day_high, day_low | raw MCX bullion feed (E6), kept apart so evening ticks never stretch an NSE replay |
| `candles_1m` | key, minute_ts, o, h, l, c, v, synthetic, bv, sv | index and bullion candles, keyed by instrument; bv/sv = buyer-/seller-initiated volume (E8, migration 012), NULL with no side information |
| `chain_minutes` | idx, minute_ts, strike, ce_* / pe_* (ltp, oi, oi_chg_open, iv, buildup), atm, pcr, max_pain | per-strike per-minute chain snapshot |
| `bias_minutes` | idx, minute_ts, bias, label, strength, breakdown_json | evidence history (indices and GOLD / SILVER) |
| `signals` | the `Signal` fields (§9.2), with `index` stored as `idx` | every signal, live and shadow, index and bullion |
| `signal_outcomes` | signal_id, end_ts, result, result_ts, best/worst price and ts, px_1m/5m/15m, spot_at_fire, spot_pre_move, spot_best_move, final | what each index signal's option did next (§9.5) |
| `config_versions` | version, tag, created_ts, source, reverted_from, params_json | every saved parameter set (§3.2) |
| `paper_trades` | id, signal_id, idx, instrument_key, trading_symbol, direction, strike, expiry, lots, qty, signal_entry, entry_price, entry_ts, slippage, target_price, stop_price, cost, status, exit_price, exit_ts, exit_reason, exit_fill_quality, exit_price_age_ms, gross, net, warning, blocked, banked | index and bullion paper trades; `blocked` and `banked` are the paper bank's (§10.5) |
| `bank_ledger` | id, ts, kind, amount, opening_balance, config_version | one cash move in the paper bank: the opening deposit, then a deposit or withdrawal per change of the opening balance (§10.5) |
| `app_state` | key, value | small application state; unused since migration 014 removed E15's `factors_off` |
| `gift_nifty` | day, ref_ts, ref_close, preopen_ts, preopen_price, fetched_at | GIFT Nifty's previous-close and pre-open prices per NSE day (E14, §6.8); read by replay and `tools/score.py` |
| `feed_events` | ts, kind, detail | session starts, disconnects, gaps, bullion gaps, recentres, backfills, tick prunes |
| `latency_samples` | ts, hop, p50, p95, p99, n | one row per hop per minute |

Indexes on `(key, ts)` for ticks and candles, `(idx, minute_ts)` for chain and bias.
Schema managed with plain versioned SQL migrations applied at startup.

Volume estimate: ~45 instruments × ~2 ticks/s × 6.25 h ≈ 2 M tick rows/day ≈ 150 MB/day
uncompressed. Nothing is pruned automatically; the trader prunes ticks up to a chosen date
from the Data panel (§10.4). The database uses `auto_vacuum = INCREMENTAL` so pruned space
is reclaimable without a full rewrite.

---

## 12. API

### 12.1 REST (`/api`)

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | app, auth state, feed health, NSE market status, feed live, the banner, and the `bullion` status (§6.6) |
| GET | `/auth/login` | 302 to Upstox |
| GET | `/auth/callback` | handles code, starts the feed, 302 to `/` or `frontend_url` (§4) |
| GET | `/instruments` | resolved spot/futures/expiry/window per index |
| GET | `/chain/{index}` | current `ChainState` snapshot + derived values |
| GET | `/stats/{index}` | `IndexStats` for the details view (§7.4) |
| GET | `/candles/{index}?minutes=375` | today's spot candles with EMA/VWAP/supertrend series, and `fut_candles` (the near-month future's, whose `bv`/`sv` give net volume) |
| GET | `/bias/{index}` | latest bias + breakdown |
| GET | `/bias/{index}/history?day=` | per-minute bias for a day |
| GET | `/signals?index=&status=&day=` | signals of a day (index and bullion) |
| GET | `/signals/active` | signals that can still be paper-traded, with their `live` levels |
| GET | `/signals/gates` | the last gate result per index and metal |
| GET | `/signals/scorecard?from=&to=&index=` | how the signals of a date range turned out, per entry rule (§9.5); today by default |
| GET | `/flow` | latest order-flow reading per index (§8.5) and whether it is live or shadow |
| GET | `/signals/{id}` | one signal with breakdown and outcome |
| POST | `/paper-trades` | body `{signal_id}` → trade |
| POST | `/paper-trades/{id}/close` | manual close |
| GET | `/paper-trades?index=&status=&from=&to=` | trades |
| GET | `/journal/stats?from=&to=&index=` | summary stats: overall (index options), per index, `bullion` and per metal |
| GET | `/bullion` | the GOLD / SILVER snapshot (§6.6) |
| GET | `/bullion/{metal}/candles` | today's bullion candles with VWAP |
| GET | `/parameters` | the config in force: version, tag, created_ts and the `ParameterSet` |
| GET | `/parameters/schema` | one entry per editable value: path, group, kind (number, integer, choice, time), limits, choices, help |
| PUT | `/parameters` | `{tag, params}`: saves a new version; 200 with it, or 422 with field errors (nothing saved) |
| GET | `/parameters/versions` | every version, newest first, with `active` on the one in force |
| GET | `/parameters/versions/{n}` | one version with its stored values; 404 if there is none |
| POST | `/parameters/versions/{n}/revert` | `{tag?}`: saves version n's values as a new version; 422 if n is unknown or already in force |
| PUT | `/parameters/factors/{scope}/{name}` | `{enabled}`: flips one factor switch as its own version (§8.4); 422 for an unknown scope or factor; no new version when already so |
| GET | `/data/usage?until_date=` | DB size, tick rows/days total, and what a prune up to `until_date` would remove |
| POST | `/data/prune-ticks` | body `{until_date}` → deletes ticks up to and including that date; returns rows removed |
| GET | `/metrics` | latency p50/p95/p99 per hop (last 1 and 15 min), event-loop lag |
| POST | `/metrics/client` | the browser's per-minute latency summary (receive and paint hops) |

Errors: FastAPI's JSON `{"detail": "…"}`. 404 for an unknown signal or trade; 409 when a
paper trade is requested for a signal that is no longer active or is shadow, outside its
market's hours or after its square-off, or while its feed is not live; the `detail` says
which.

### 12.2 WebSocket (`/ws`)

Server → client JSON frames `{type, ts, payload}`:

| type | cadence | payload |
|---|---|---|
| `hello` | on connect | full snapshot: health, instruments, prices, chain per index, candles, bias (indices and metals), parameters, active signals, today's signals, gates, flow, today's trades, index stats, bullion snapshot and candles, news |
| `stats` | checked once a second, sent when it changed | `IndexStats` |
| `tick` | leading-edge throttle, max 20/s per index | `{index, spot_ltp, spot_ts, fut_ltp, fut_ts}` |
| `chain` | leading-edge throttle, max 2/s per index | full window (21 rows) + derived values; small enough that diffs are not worth it |
| `candle` | per minute | closed candle (`role` spot or fut; every candle carries `bv`/`sv`) |
| `bias` | per minute | bias + breakdown, the chart `overlay` and the current `gates` |
| `signal` | on change | full `Signal` with the current gates, shadow ones included (flagged) |
| `signal_live` | 1/s while any signal is active | the active signals with their `live` levels (§9.3) |
| `flow` | about 1/s per index | order-flow score and its three parts (§8.5) |
| `paper_trade` | on change, and 1/s while open | trade with live P&L |
| `health` | on change | feed/auth/market status, banner, bullion status |
| `bullion` | leading-edge throttle like `tick` | the GOLD / SILVER snapshot |
| `bullion_candle` | per closed bullion minute | `{metal, candle, overlay}` |
| `parameters` | on a save or revert | version, tag, created_ts, the set, effective-from minute |
| `news` | on change (at most once per poll, §6.7) | `NewsOut`: status, error, fetched_at, headlines newest first |

Every frame carries `t_src` (exchange ts), `t_in` (backend ingest), `t_out` (backend send)
so the client can compute per-hop latency. Frames are serialised with pydantic and the
standard `json` module; throttled channels send only the latest state of the window.

Client → server: `{"type":"ping"}` only, answered with a `pong` frame. All mutations go through REST.

On reconnect the client receives a fresh `hello`, so no event replay is needed.

---

## 13. Frontend

### 13.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TradeDisha  ● LIVE 11:42:07  Feed: connected (0.4s)  Login: valid  [Journal] │
├────────────────────────────────────────────────┬─────────────────────────────┤
│  [NIFTY]  [BANKNIFTY]                          │ OPTION CHAIN             [–]│
│  ┌ INDEX ─────────────────────────────── [–] ┐ │ NIFTY  17/11/2026           │
│  │ Spot 24,512.40  Fut 24,548.10             │ │ PCR 1.18   Max pain 24500   │
│  │ [AUTO 24,512 +0.82%] [IT 37,880 +1.24%] … │ │                             │
│  │ ▸ Details                                 │ │─────────────────────────────│
│  └───────────────────────────────────────────┘ │ OI ΔOI IV LTP │STRIKE│ LTP… │
│  ┌ SIGNAL ────────────────────────────── [–] ┐ │ ...                         │
│  │ BUY NIFTY 24500 CE   Live 142.5 T 185.3   │ │ ▌ 24500 ATM row highlighted │
│  │ Fired 140.0 T 182.0 S 119.0  04:12 left   │ │ ...                         │
│  │ [ Paper trade ]                           │ │                             │
│  └───────────────────────────────────────────┘ │                             │
│  ┌ MARKET VIEW ───────────────────────── [–] ┐ │                             │
│  │ Bearish ─────────┼──────▮ Bullish  62 Bul.│ │                             │
│  │ ───────────────────────────────────────── │ │                             │
│  │ EMA 9/21 cross   +0.71   0.133   +0.095   │ │                             │
│  │ …  Order flow +0.31                       │ │                             │
│  └───────────────────────────────────────────┘ │                             │
│  ┌ PRICE CHART ───────────────────────── [–] ┐ │                             │
│  │ 1-min candles, EMA9/21, VWAP, ▲▼ markers  │ │                             │
│  │ net volume ▆▂▇▃ (E8)                      │ │                             │
│  └───────────────────────────────────────────┘ │                             │
│  ═══════════ drag: chart height ═════════════  │                             │
│  ┌ OPEN PAPER TRADES ─────────────────── [–] ┐ │                             │
│  │ 24400 PE ×75  98.0 → 85.5  −₹938  [Close] │ │                             │
│  └───────────────────────────────────────────┘ │                             │
│  ┌ SIGNALS TODAY ─────────────────────── [–] ┐ │                             │
│  │ 11:38:00  24500 CE  142.5  …  active      │ │                             │
│  └───────────────────────────────────────────┘ │                             │
└────────────────────────────────────────────────┴─────────────────────────────┘

A minimised panel is its title bar alone, with a one-line summary:
  ┌ PRICE CHART  last 24,512.40 ─────────── [▾] ┐
```

Minimum supported width 1280 px. The chain panel and the price chart are resizable (see
"Resizable layout" in §13.2). Every panel can be minimised ("PanelFrame" in §13.2).
The main column scrolls; its panels come in the order drawn above until the trader moves
them ("Panel order" in §13.2).

**Right column with headlines (Milestone E10).** The right column holds the option chain on
top and Headlines (§6.7) below it, with a horizontal drag divider between them:

```
NIFTY / BANK NIFTY tab               Chain minimised        BULLION tab
┌────────────────────────┐           ┌──────────────────┐   ┌──────────────────┐
│ OPTION CHAIN       [–] │           │ OPTION CHAIN [▾] │   │ HEADLINES  [–][×]│
│  strikes …             │           ├──────────────────┤   │ TODAY            │
├────── drag ────────────┤           │ HEADLINES  [–][×]│   │▌09:50 SBIN BHART…│
│ HEADLINES      [–][×]  │           │ TODAY            │   │▌SENSEX up 400 …  │
│ TODAY                  │           │▌09:50 SBIN BHART…│   │ YESTERDAY        │
│▌09:50  SBIN BHARTIARTL │           │▌SENSEX up 400 …  │   │ 15:58 ITC BHARTI…│
│▌SENSEX up 400 pts, …   │           │ YESTERDAY        │   │ Market wrap …    │
│ YESTERDAY              │           │ 15:58 ITC …      │   │                  │
└────────────────────────┘           └──────────────────┘   └──────────────────┘
▌ = unseen (accent bar). Earlier days' rows are muted.
```

- Both expanded: the chain fills, headlines take the remembered height.
- One minimised: it is its title bar and the other fills the column.
- Headlines hidden (×, or the top bar's Headlines toggle): the column is the chain alone,
  as before E10.
- Nothing expanded (chain minimised or absent, headlines minimised or hidden): the column
  becomes the 28 px strip; its button expands both and shows headlines again.
- BULLION tab: there is no chain, so the column shows headlines alone (it was absent
  before E10); with headlines hidden there is no column.

### 13.2 Components
- **TopBar**: market status pill (pre-open / live / closed / holiday, with clock), feed
  health with tick age colour (green < 2 s, amber < 10 s, red otherwise), auth state with
  Login button, Journal link. Both pills follow the tab (E5): on an index tab they read NSE
  status and the newest index tick; on BULLION they read `MCX LIVE` / `MCX CLOSED` and the
  newest bullion tick. While that market is closed, a quiet feed is shown muted instead of
  amber or red; a dropped connection is always red.
- **StatusBanner**: one band under the top bar. Errors (login, feed gap, lost backend) are
  red with ⚠. A market's session state (closed, holiday, pre-open; NSE, or MCX on
  BULLION) is an amber band with ⏸ and a bold title such as "NSE MARKET CLOSED", so it
  is never mistaken for a quiet feed (E5). On BULLION the bullion status decides the
  banner; login and connection problems still come first.
- **IndexTabs**: NIFTY / BANKNIFTY, and BULLION while there is bullion data (§6.6);
  selection drives chart, meter, signal, evidence, and chain panel. A selected BULLION
  survives a reconnect, and falls back to the first index if bullion goes away.
- **BULLION tab** (Milestones E4, E6). The main column's panels, the same units in the same
  trader-set order with the same ↑ ↓ and minimise controls as the index tabs, for the metal
  picked by a GOLD / SILVER switch above them (`MetalSwitch`, remembered in `localStorage`
  as `tradedisha.bullionChart`). The tiles unit is `BullionCards` (below) instead of the
  index tiles; Market view, Signal, Price chart, Evidence (trend, OI, flow and macro groups;
  no order-flow line), Open paper trades and Signals today show the metal (§9a). The option-chain column
  and its divider are not shown.
- **BullionCards** (the BULLION tiles):
  - A card per metal, headed by the contract, expiry and lot:
    - LTP with unit, change and change % (always shown)
    - a **Details** toggle, like the index tile's, closed by default; one choice for both
      cards, remembered in `localStorage` (`tradedisha.bullionDetailsOpen`, apart from the
      index's `tradedisha.detailsOpen`). Opened, it shows:
    - Today: open, high, low with range bar, previous close, ATP
    - Liquidity: volume, OI, bid and ask with quantities, spread, buy/sell quantity and ratio
    - Contract, 1 year: high and low with distance and range bar, circuit limits
    - Next month: price, spread over near
  - The gold/silver ratio.
  - `Price`, `Group`, `Fact` and `RangeBar` are shared with IndexTiles (`components/Facts`).
- **IndexTiles**: spot and futures for the selected index; under them the **Sectors**
  block (E11), which opens and closes like Details (open by default, remembered as
  `tradedisha.sectorsOpen`; closed, it shows how many sectors are up and down, e.g.
  `6 up · 4 down`). Open, it is a small box per sector in config order with three lines:
  name (normal size, semi-bold, full text colour, to be easily read), value (flashing on
  each tick like spot), and
  change in points with change % in brackets, `+464.00 (+1.24%)` (green up, red down,
  muted at zero; "—" without a price). Two boxes across narrow, three on small and five
  on medium screens and up (NIFTY's ten in two rows); the full name and previous close on
  hover; no block for an index with no sectors. Then a collapsible
  **details view** showing `IndexStats` (§7.4) in six groups: options (ATM and the number
  of strikes in the chain window, moved here from the top row in E11); day open / high
  / low with a small range bar marking the current price; 52-week high / low with the
  distance of the current price from each; previous close with change and change %;
  futures premium over spot; India VIX with its change %. Closed by default *(my call)*;
  a chevron button toggles it and the state is remembered. Missing values render as "—".
  The view follows the index tabs; VIX is the same in both. NIFTY shows ten sectors,
  BANK NIFTY its three bank sub-indices.
- **Resizable layout**: two draggable dividers *(my call)* — a vertical one between the
  main column and the chain panel, and a horizontal one under the price chart setting its
  height. Each is a 4 px handle with a wider hit area, `role="separator"`, keyboard
  arrows move it, double-click resets to the default. Limits: chain panel 420–900 px and
  never more than 60% of the window; chart 200–700 px. Sizes are stored in `localStorage`
  and clamped again on load and on window resize, so a layout saved on a large screen
  cannot hide a panel on a small one. Dragging is throttled to one layout per animation
  frame. No library is added for this. E10 adds a third, horizontal, between the chain
  and Headlines in the right column (headlines 120–900 px), shown only while both are
  expanded.
- **PanelFrame**: the frame around each of the eight dashboard panels (`tiles`, `bias`
  "Market view", `signal`, `trades`, `chart`, `history`, `chain`, `news` "Headlines"). It owns the box and a
  32 px title bar with the panel's title and one minimise / expand button; the panel
  components inside draw no box or duplicate heading of their own. Minimised, only the
  title bar is left, with a one-line summary (`lib/panelSummary.ts`: spot and change;
  strength and label; signal with entry and time left; open trades with live P&L; last
  close; signals today; PCR and max pain), and the panels below move up. Contents
  are not rendered while minimised, except the price chart, which is kept in the page
  hidden so its zoom survives. The state is remembered in `localStorage`
  (`tradedisha.panels`); the E1 key `tradedisha.chainOpen` seeds the option chain's state
  the first time. There is no full-screen state (built, then removed at the owner's
  request).

  The bias meter and signal card share a row; when either is minimised the row becomes
  one column. The chart-height divider is rendered only while the chart is expanded. A
  "Restore panels" button in the TopBar appears while any panel is minimised and expands them all; E1's sizes are
  untouched. State is shared across the index tabs. *(These are the builder's calls.)*
  A minimised `signal` panel opens itself when an active signal id not seen in this page
  load arrives, and `trades` likewise for an open trade id; minimised again, it stays
  down until the next new id.
- **Panel order** (Milestones E3, E9): the main column is six panels, each moving on its
  own, drawn in a remembered order; the default is `tiles`, `signal`, `bias` (Market
  view: the meter with the evidence table and order-flow line below it, full width),
  `chart` (with its height divider), `trades`, `history`. Each PanelFrame has move-up and
  move-down buttons beside minimise; the button with nowhere to go is disabled. The index
  tabs and the option chain do not move. The order is kept in `localStorage`
  (`tradedisha.panelOrder`); a stored list is read tolerantly (unknown and repeated ids
  dropped, missing units added at the end). An order stored before E9 is carried over:
  the old `view` pair becomes `signal`, `bias` in its place and the old `evidence` unit is
  dropped; a stored `evidence` minimised flag is ignored. "Restore panels" also resets the order and is
  shown while it differs from the default. Units are keyed, so a moved chart is not
  remounted and keeps its zoom. `lib/panels.ts` holds the order logic.
- **SidePanel** (the right-hand column holding the option-chain PanelFrame): minimising
  the chain hides the column, leaving a 28 px strip on the right edge with a "show"
  button and the panel's name; the main column takes the freed width (the chart resizes
  with it). The divider is not rendered while hidden, and the remembered width is used
  again on show. Hidden means not rendered only: the chain keeps updating in the store,
  and indicators, signals and recording are unaffected. Since E10 the column also holds
  Headlines and its rules are in `RightColumn` (§13.1 "Right column with headlines"); the
  strip appears only when nothing in the column is expanded.
- **Headlines** (Milestone E10, §6.7): a scrolling list, newest first, grouped by IST day
  under sticky headers: Today, Yesterday, then `Fri 14/11`. Each row: time (`HH:MM`; the
  day is in the header), the stock symbols as chips, the heading as a link opening the
  article in a new tab (`rel="noopener noreferrer"`; a link that is not http(s) is shown
  as plain text), and the summary behind a click (`aria-expanded`). No thumbnails.

  Colour (`lib/news.ts`), never green or red, which mean bullish and bearish here:
  - Freshness: the time is accent within the last hour, normal earlier today; an earlier
    day's row (time and heading) is muted, and so is its header.
  - Unseen: an accent bar down the row's left edge (`lib/useNewsSeen.ts`). While the list
    is on screen the newest headline is recorded as seen (`tradedisha.newsSeen`), but the
    bar is measured against what had been seen when the panel opened, so a new headline
    keeps its bar until the panel is next opened; nothing is unseen on a first visit.
  - Chips by index, from the stock list: violet (`--index-bank`) for a BANK NIFTY stock,
    whether or not it is also in NIFTY; a neutral tint for NIFTY only; muted for a stock
    with no index given. The chip's tooltip names its indices.

  Stale-price dimming applies to the chain only, never to the headlines. States: "News needs the Upstox login", "Loading
  headlines", "No headlines in the last 7 days", and a muted error line under the last
  good list. Minimised, the summary is the new count and the newest headline. The panel id
  is `news`; it does not move. Hidden is its own remembered flag (`tradedisha.newsHidden`),
  set by the frame's × button (`PanelFrame.onClose`) or the TopBar's Headlines toggle;
  "Restore panels" clears it. Its height is `newsHeight` in the stored layout (default
  280 px, 120–900, clamped like the others; a layout stored before E10 gets the default).
- **BiasMeter**: horizontal gauge −100…+100 with label and strength; animates on update.
- **PriceChart**: resizes with its container (it has no fixed height once the layout is
  resizable). `lightweight-charts` candlestick; EMA9, EMA21, VWAP line series;
  supertrend as coloured line; signal markers (▲ CE, ▼ PE) with tooltips; paper-trade
  entry/exit markers. A second pane below shows **net volume** per minute (E8): a
  histogram of buy − sell volume, green above zero and red below, from the near-month
  future on index tabs and the metal's future on BULLION. The legend gives net, buy and
  sell for the minute under the crosshair (or the latest); minutes without side data have
  no bar.
- **SignalCard**: direction, symbol, the Fired and Live rows of entry/target/stop (E7;
  points shown on expiry day; a future shows its rupees per point), countdown, an
  open-trades block when there are open trades on that index or metal (each with
  direction, entry, live P&L and minutes open; closing is done from the OpenTrades panel), Paper
  trade button (disabled with reason when market closed, feed not live, or signal not
  active), link to full breakdown. With no active signal it says so, with the reason the
  last minute did not fire.
- **OpenTrades** (the "Open paper trades" panel): one row per open paper trade on the
  selected index: option and quantity, entry, current price, target, stop, live net P&L,
  time open, a "bias reversed" flag, and a Close button (disabled while the feed is not
  live). Always on the page; with none open it reads "No open paper trades." It sits
  second last in the main column, directly above Signals today *(owner's decisions,
  2026-11-13)*. Its border takes the accent colour while a trade is open.
- **SignalHistory** (the "Signals today" panel): today's signals on the selected index:
  time fired, option, entry, target, stop, bias strength, status with the time it changed,
  and the outcome (§9.5): target, stop, neither or "following", with the best and worst
  move. A line above the table counts the day's scored signals by result. Shadow signals
  (§9.6) are listed greyed and tagged, with their own count line; they are not drawn on
  the chart.
  Last in the main column.
- **EvidenceTable**: one row per indicator: name, note, raw values on hover, score bar,
  weight, contribution; greyed when `quality != ok`; group subtotals; expiry-day banner.
  Each factor row carries a read-only ON/OFF label (`FactorSwitch` without `onChange`),
  with "(off from the next minute close)" or "(on from …)" while the bias shown predates
  a flip; a footer counts the factors switched off ("Change in Config, Factors.").
  Under it, the **FlowLine**: the order-flow score and its three parts (§8.5), marked
  "recorded only, not used for signals yet" while the trigger is the shadow rule.
- **OptionChain**: virtualised table, ATM centred and highlighted, OI build-up heat
  shading (log scale of ΔOI), build-up class badge on hover, header with expiry, PCR,
  max pain, last update time.
- **Journal page**: filterable trade table (index, date range, exit reason, fill
  quality); non-`live` fills badged; summary cards (hit rate, net P&L, avg win/loss,
  trades) overall and per index; click-through to the originating signal's breakdown.
- **Data panel** (drawer from the TopBar): DB size, tick days held, oldest/newest tick
  date; a date picker for "delete ticks up to and including"; a preview line ("N days,
  M rows, ~X MB") fetched from `/data/usage`; a confirm step that requires typing the date;
  progress and result. Derived data is stated as unaffected.
- **Config control** (in the TopBar): a button showing the version and tag in force
  ("Config v7 higher bar"). It opens a **drawer on the right** over a dimmed backdrop
  (since 19/11/2026; it was a dropdown panel). Its header reads "Config  in force: v7
  higher bar, saved DD/MM/YYYY HH:MM". It closes from the header line, the **✕ Close**
  button, a click on the backdrop, or Escape. Three tabs:
  - **Parameters** (was "Edit"): a form built from `/parameters/schema`, grouped as in
    §3.2. Each field shows its name, then its help text on the line below and its limits
    ("Allowed: …") under that; a changed field is outlined and shows its previous value
    ("was 0.5"). Saving needs a tag and at least one change; the server's field errors
    appear beside the field, its group or the tag, and the draft is kept. Discard drops
    the draft. After a save the bar shows "applies from HH:MM". When a new version arrives
    (a save, a factor flip or a revert), values the trader has not touched follow it and
    unsaved edits are kept.
  - **Factors · N off**: the factor switches (§8.4), one section per index and metal
    (NIFTY, BANK NIFTY, GOLD, SILVER) with its count of factors off. Each row has the
    toggle, the factor's name and a one-line plain explanation below it (`FACTOR_HELP` in
    `lib/factors.ts`); a factor switched off is dimmed. A flip is saved at once as its own
    version; "saving…" shows while it is in flight.
  - **Versions** (was "History"): every version, newest first, with its date, time and
    source (from params.toml, edited, revert to vN); the one in force carries an "in
    force" badge and the others a Revert button, which asks for a tag (pre-filled "Revert
    to vN") and a confirmation.
  There is no "Reload config" button.
- **ConfigVersionChip**: "v7" beside a signal in the signal card and in the Config column
  of "Signals today"; nothing for a signal with no version. Hovering or focusing it opens
  a panel, fixed to the window so the scrolling column cannot clip it, with that
  version's tag, when it was saved and all its values; values that differ from the
  config in force are highlighted and their tooltip gives the current value. A version
  is fetched once and cached, since versions never change.

### 13.3 Visual design
- **Theme**: dark default, light toggle, persisted in `localStorage`; design tokens
  (colour, spacing, type scale) in one Tailwind config so both themes derive from the same
  scale. Bullish green / bearish red / neutral slate, with a colour-blind-safe alternative
  (blue/orange) as a token swap.
- **Dates**: every date shown is DD/MM/YYYY, produced by one `fmtDate` helper in
  `lib/format.ts` that accepts an ISO date string or epoch ms (IST). This covers the
  journal's Date column, option and futures expiry on the tiles, signal card and chain
  header, the replay day in the top bar, and the Data panel (oldest/newest day, preview,
  result). Dates stay ISO on the wire, in the config file and in file names. Native date
  pickers follow the browser's locale and are not overridden *(my call)*; the Data panel's
  typed confirmation asks for, and accepts, the date as it is displayed.
- **Density**: tabular numerals, 12–13 px data rows, 4 px vertical rhythm in the chain;
  the whole dashboard fits 1440 × 900 without scrolling.
- **Motion**: value changes flash subtly (120 ms) and the meter eases over 300 ms; nothing
  animates continuously.
- **Performance**: chain rows virtualised; incoming WS frames are merged into stores and
  rendered once per animation frame; chart uses canvas (`lightweight-charts`) and receives
  only the changed bar; heavy components memoised; no layout thrash on tick.

### 13.4 State and data flow
- WS client with exponential reconnect; on `hello` replaces all live stores.
- One Zustand store (`state/store.ts`), keyed by index name where it varies: `prices`,
  `lastFrameAt`, `chains`, `candles`, `futCandles`, `overlays`, `bias`, `signals` (the
  active one, with `live` levels), `gates`, `flow`, `stats`; plus `ws`, `instruments`,
  `selectedIndex`, `trades`, `signalHistory`, `health`, `parameters`,
  `parametersEffectiveFrom`, `bullion`, `bullionCandles`, `bullionOverlays` and `news`.
  GOLD and SILVER use the same per-name maps as the indices.
- Per-browser preferences in `localStorage`, read through one small hook with a
  try/catch fallback to defaults: theme (existing), `layout` (`{chainWidth, chartHeight}`),
  `panels` (which panels are minimised; replaces E1's `chainOpen`, which is read once to
  carry the choice over), `panelOrder` (the order of the main column's units),
  `detailsOpen`, `bullionDetailsOpen`, `sectorsOpen`, `bullionChart` (the metal picked),
  `newsHidden` and `newsSeen`. All keys are prefixed `tradedisha.`.
- REST via plain `fetch` (`api/client.ts`) for history, the journal and mutations
  (`POST /paper-trades`).
- Optimistic UI is not used for paper trades; the button shows a spinner until the server
  confirms, because the fill price comes from the server.

---

## 14. Time, calendar, and operating modes

- `MarketClock` provides `now()` and `status()` ∈ `pre_open | live | closed | holiday`
  from IST time and an NSE holiday list (static file for the year, editable). A second
  `MarketClock` on the same time source, `FeedSession.mcx_clock`, does the same for MCX
  with its own hours and calendar, including evening-only days (§6.6).
- **Clock source.** `MarketClock` is injected everywhere time is read (engine, paper
  manager, square-off timer, signal TTL). In live mode it reads the wall clock. In replay
  mode it is driven by the replayed tick timestamps, so a session replayed at 21:00 still
  sees "09:15–15:30" and the engine, cut-offs, and square-off behave exactly as they did
  live. No component reads the wall clock directly; the only exception is `main.py`, which
  seeds the replay clock at start. This is a convention kept in review (no lint rule
  enforces it).
- Modes:
  - **live**: auth valid, market live → feed connected, engine running.
  - **standby**: NSE closed or holiday → no index ticks expected; the UI shows the last
    known state under an amber "NSE market closed" (or holiday) banner, and a quiet index
    feed is not an outage. With the live feed the socket stays up for MCX bullion until
    MCX closes. Replay is started by restarting with `feed_provider=replay`.
  - **degraded**: market live but auth missing/expired or feed disconnected → banner with
    the reason; last-known data shown with greyed timestamps; bias still computed from
    whatever candles exist but shown greyed; no new signals; paper-trade entry and manual
    close refused (409); target/stop not evaluated until the first tick after resume
    (then marked `after_gap`); the square-off timer still fires and closes at the last
    known LTP marked `stale`. Entering and leaving degraded mode are recorded in
    `feed_events` with the gap duration.
  - "Feed live" means connected and an **index** (NSE) tick within
    `feed_live_max_tick_age_ms`. MCX bullion ticks on the same socket do not count (§6.6).

---

## 14a. Performance and latency

### Budget (p95, measured continuously)

| Hop | Budget |
|---|---|
| Exchange timestamp → backend ingest (network + Upstox) | not under our control; reported |
| Ingest → tick bus fan-out complete | 2 ms |
| Ingest → WS frame sent | 50 ms (leading-edge throttle at 20 Hz, polled every 12 ms, so a fresh tick leaves within ~12 ms and a coalesced one within 50 ms) |
| WS sent → client store updated | 20 ms |
| Store updated → painted | one animation frame (≤ 16 ms) |
| **Ingest → painted, total** | **< 250 ms** |
| Minute close detected → bias + signal computed | 30 ms |
| Minute close detected → signal painted | **< 100 ms** |

The clock starts at **arrival at the app** (`t_in`), not at the exchange timestamp
(Anuj's decision): the broker→app hop is reported as its own row in the overlay and
`/metrics` but is not part of the budget. "Minute close detected" is the moment the candle
builder closes the candle: normally the first tick of the next minute, or the 2 s
wall-clock fallback when ticks are sparse; the detection delay is reported separately as
`minute_close_lag`.

### Backend techniques
- uvicorn's standard event loop (uvloop where installed); JSON through pydantic and the
  standard library; protobuf decode in the feed task only.
- The tick bus is a synchronous fan-out; consumers never block. SQLite writes are kept
  off the per-tick path: ticks are buffered and written in batches (500 rows, or the
  twice-a-second flush).
- Chain derived values are recomputed over the window on each tick that changes OI or
  LTP (§7.2); with at most 21 rows this is cheap.
- WS push is throttled per channel (§12.2) on the leading edge and coalesced: a dirty
  index is pushed as soon as its minimum gap has elapsed and the latest state wins, so a
  slow client never builds a backlog. Candle, bias and parameter frames bypass the throttle
  and go out on the next pusher pass.
- Indicators recompute over the candle window (<= 400 bars) at each minute close rather
  than carrying incremental state; measured cost is microseconds and the functions stay
  pure. Revisit only if the instrument count grows by orders of magnitude. A client with
  64 frames queued (`SLOW_CLIENT_LIMIT`) is closed with code 1008 ("client too slow") and
  reconnects to a fresh `hello`.
- Event-loop lag is sampled every 100 ms and reported as the `loop_lag` hop in `/metrics`
  and the dev overlay.
- Replay at `speed=0` is used as the load test: a full day must process in under 60 s on
  the development Mac.

### Frontend techniques
See §13.3 Performance. Additionally: WS parsing in the main thread (frames are small);
React 19 automatic batching; no state in context that changes per tick; `React.memo` on
chain rows keyed by strike; chart updates via `series.update()` not `setData()`. The
production build (`vite.config.ts`) splits the libraries from the app's code: `charts`
(`lightweight-charts`), `vendor` (React, Zustand) and the app, so no file passes Vite's
500 kB warning and the library files stay cached when only the app changes.

### Measurement
- Every WS frame carries `t_src`, `t_in`, `t_out`; the client stamps `t_recv` and
  `t_paint` (via `requestAnimationFrame` after store commit) and posts a per-minute
  summary to `POST /api/metrics/client`.
- `/api/metrics` and the dev overlay (toggle with `?debug=1`) show per-hop p50/p95/p99.
- Per-minute summaries are stored in `latency_samples` so a slow afternoon can be
  diagnosed afterwards.

## 14b. Code quality standards

- **Python**: ruff (lint + format; rules `E F W I N UP B SIM PL RUF ANN ASYNC T20 PT`,
  at most 8 arguments, line length 100), mypy `--strict` with the pydantic plugin over the
  package and the tests, no `Any` in public signatures, pydantic models at the API and
  settings boundaries, pure functions for all trading maths, docstrings on public
  functions stating units and conventions (IST vs UTC, % vs fraction). Modules are aimed at
  ~300 lines; `market/session.py` (~950) and `engine/signals.py` (~520) are over it and are
  candidates to split.
- **TypeScript**: `strict: true`, ESLint (typescript-eslint strict + react-hooks +
  jsx-a11y) with zero warnings, Prettier, no `any`. API types are a hand-written mirror of
  `api/schemas.py` and the WS frames in `frontend/src/api/types.ts`; both sides change
  together.
- **Structure**: dependencies point inward: `api` → `engine`/`market` → `store`;
  `indicators` imports nothing from `api`, `feed` or `store`. Kept by convention (no tool
  enforces it).
- **Tests**: see §15. Trading logic is written test-first, with table-driven lifecycle
  tests and property tests for score bounds. Coverage is not measured.
- **Automation**: pre-commit runs ruff (with `--fix`), ruff format, mypy, ESLint, Prettier
  and tsc over the whole project (not the tests); `make check` (`scripts/check.sh`) runs
  every gate plus the backend and frontend tests; a milestone is not "done" with it red.
- **Conventions**: one way to do each thing (one HTTP client, one time helper, one event
  bus); no feature flags for dead code; TODOs carry a milestone reference or are not
  committed.

## 15. Testing strategy

| Layer | Approach |
|---|---|
| Indicators | pure-function unit tests on synthetic candle/chain series with known answers; property tests for score bounds |
| Chain derived values | fixtures of recorded chain minutes with hand-verified PCR / max pain |
| Candle builder | tick fixtures covering gaps, out-of-order ticks, minute boundaries |
| Signal engine | table-driven lifecycle tests: fire, lapse, reversal, hysteresis, time cut-offs, expiry-day mode, open-trade interaction |
| Paper trading | every exit path, slippage recording, cost netting, square-off timer, degraded-mode behaviour (entry refused, `after_gap` and `stale` fills), warning set/clear on bias change |
| Tick pruning | preview matches deletion; derived tables untouched; prune during live append; vacuum reclaims space |
| Integration | replay recorded ticks through the full session (fault injection, a recorded live day, a bullion evening) and assert the persisted results; there is no golden-file comparison |
| API | FastAPI test client for REST contracts; WS `hello` and per-second frames |
| Frontend | Vitest component tests beside each component (SignalCard states, EvidenceTable, TopBar, StatusBanner, BullionView, …) and store tests; no browser end-to-end suite |
| Bullion | parameters, four-group aggregation (trend, OI, flow, macro), the offset queue, the signal gates and lifecycle, short P&L, MCX square-off, ownership on restore, recording and replay |
| Fault injection | replay provider configured to drop/delay ranges; assert reconnect, re-subscribe, and degraded-mode behaviour |

Live verification per milestone is described in plan.md.

---

## 16. Security and safety notes

- Upstox credentials and tokens are read from `.env` and SQLite in `data/`, both
  gitignored. Nothing is sent anywhere except Upstox.
- The backend binds to `127.0.0.1` only.
- There is no order-placement code. The Upstox client wrapper exposes only auth, market
  data, instrument, and candle endpoints; order endpoints are not implemented.

---

## 17. Open items to resolve during build

| Item | Resolve in | Fallback | Status |
|---|---|---|---|
| Exact Upstox WS protobuf schema, `full` mode fields, subscription cap | M1 | reduce `strike_window` | resolved: live feed in use |
| Whether IV/delta arrive on the feed | M2 | compute via Black-Scholes (§7.3) | resolved: delta computed when absent; IV from the feed |
| Whether option-chain REST provides day OI change for opening-OI backfill | M2 | `oi_baseline=partial` flag | resolved in M6 backfill |
| Intraday candle REST availability for same-day minutes | M3 | warm-up period with `quality=warming` | resolved: used for backfill |
| Indicator constants (k, bands) | M3 review point | tune on recorded days | open: tuned with `tools/score.py` as days accumulate |
| 52-week high/low from daily candles matches NSE's published figures | E1 demo | show the values with their source dates on hover | resolved: checked live |
| India VIX arrives on the feed in `full` mode like the other indices | E1 demo | poll the quote API once a minute | resolved: checked live |
| `tbq`, `tsq`, `atp` and all five book levels arrive in `full` mode for index futures and the option window | S1 live day | build the trigger on whichever of them do arrive | resolved: recorded live |
| Growth of the `ticks` table with the eight order-flow columns | S1 live day (Data panel) | record them only for the futures and the strikes near ATM | watch: prune from the Data panel |
| Whether order flow leads price on these contracts at all | S2 shadow scorecard | keep the minute-close rule; try enhancement 6's other options | open: S3, after five live sessions |
| MCX ticks (and the `1d` OHLC row) arrive for this account in `full` mode | E4 live check | poll the full quote once a few seconds | resolved: checked live 2026-11-16 |
| A live bullion signal and paper trade behave as the tests say | E6 live check | tune `bullion.*` | open: bias and panels checked live, a trade still to see |
