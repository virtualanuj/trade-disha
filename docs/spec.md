# TradeDisha — Architecture and Design Specification

Requirements: [intent.md](intent.md). Milestones: [plan.md](plan.md).
This document describes how the first version is built. Values marked *(default)* live in
configuration and can be changed without code changes.

---

## 1. System overview

```
                    ┌──────────────────────────────────────────────────────┐
                    │                    Backend (Python)                   │
                    │                                                       │
 Upstox REST  ─────►│  Auth ─┐                                              │
 Upstox WS    ─────►│  Feed Adapter ──► Tick Bus ──┬─► Candle Builder ──┐   │
                    │     ▲                        ├─► Chain State ─────┤   │
                    │     │ (swap)                 └─► Tick Store       │   │
                    │  Replay Adapter                                   ▼   │
                    │                                            Signal Engine
                    │                                          (every 1-min close)
                    │                                                  │    │
                    │                               Paper Trade Manager ◄───┤    │
                    │                                                  │    │
                    │  SQLite ◄──────────── Repositories ◄─────────────┘    │
                    │                                                       │
                    │  FastAPI: REST + WebSocket push ◄─── Event Bus        │
                    └───────────────────────────┬───────────────────────────┘
                                                │ HTTP + WS (localhost)
                    ┌───────────────────────────▼───────────────────────────┐
                    │              Frontend (React, single page)            │
                    │  Top bar │ Index tabs: meter, chart, signal, evidence  │
                    │          │ Right panel: option chain │ Journal page    │
                    └───────────────────────────────────────────────────────┘
```

Single process, single user, runs on the trader's Mac. All state is in memory during the
session and persisted to one SQLite file. The frontend never talks to Upstox directly.

### 1.1 Principles
- **One way in for market data.** Every tick enters through the `MarketDataProvider`
  interface. Live (Upstox), replay (recorded ticks), and test (synthetic) providers are
  interchangeable.
- **Pure computation.** Indicators, aggregation, and signal rules are pure functions of
  their inputs. Side effects (persistence, push) happen in thin orchestrators.
- **Event-driven push.** The backend publishes domain events on an in-process event bus;
  the WebSocket layer forwards them to the browser. The frontend never polls for live data.
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
│   │   ├── config.py            # pydantic-settings; all defaults live here
│   │   ├── main.py              # FastAPI app factory, lifespan wiring
│   │   ├── auth/                # Upstox OAuth
│   │   ├── instruments/         # master download, resolution, expiry rules
│   │   ├── feed/                # provider interface, upstox, replay, tick bus
│   │   ├── market/              # candle builder, chain state, derived values
│   │   ├── indicators/          # pure indicator functions
│   │   ├── engine/              # aggregator, signal lifecycle, expiry-day mode
│   │   ├── parameters/          # ParameterSet model, versioned parameter service
│   │   ├── metrics/             # latency samples, event-loop lag
│   │   ├── paper/               # paper trade manager, exits, journal stats
│   │   ├── store/               # SQLite schema, repositories
│   │   ├── api/                 # REST routers, WS hub, DTOs
│   │   └── events.py            # event bus and event types
│   └── tests/
│       ├── fixtures/            # recorded tick/chain samples
│       └── ...
├── frontend/
│   ├── package.json
│   └── src/
│       ├── api/                 # REST client, WS client, types
│       ├── state/               # stores for market, signals, trades
│       ├── components/
│       │   ├── TopBar/
│       │   ├── BiasMeter/
│       │   ├── PriceChart/
│       │   ├── SignalCard/
│       │   ├── EvidenceTable/
│       │   ├── OptionChain/
│       │   ├── Journal/
│       │   ├── ConfigControl/   # Reload config, View config drawer
│       │   └── DebugOverlay/    # latency per hop, frame time (?debug=1)
│       └── pages/               # Dashboard, Journal
├── config/
│   └── params.toml              # starting parameters for a new database
├── data/                        # tradedisha.sqlite, instrument cache (gitignored)
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

| Key | Default | Notes |
|---|---|---|
| `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URI` | — | required for live |
| `DB_PATH` | `data/tradedisha.sqlite` | |
| `INDICES` | `NIFTY, BANKNIFTY` | |
| `MARKET_OPEN`, `MARKET_CLOSE` | 09:15, 15:30 | IST |
| `BIND` | `127.0.0.1:8000` | |
| `CANDLE_SECONDS` | 60 | |
| `RISK_FREE_RATE` | 6.5 % | for computed IV only |

All times are IST. The backend runs with `Asia/Kolkata` as its working timezone and stores
UTC epoch milliseconds.

### 3.2 Tunable parameters (`ParameterSet`)

A single pydantic model with validation (weights sum to 1, thresholds in range, fast EMA <
slow EMA, …), grouped as in the Group column below. Each field carries a one-line
description, which the editor shows as help text.

| Group | Parameter | Default |
|---|---|---|
| Weights | `w_trend`, `w_oi`, `w_premium` | 0.40, 0.35, 0.25 |
| Weights | `expiry_oi_weight_factor` | 0.5 |
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
| Chain | `strike_window`, `recenter_strikes` | 10, 2 |
| Paper | `square_off_time` | 15:15 |
| Paper | `cost_per_trade` | ₹60 |
| Paper | `lots` | 1 |

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
re-centre check.

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
  `AuthChanged(logged_in=True)`; redirects to `/`.
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
```

`FeedHealth = {state: connecting|connected|disconnected, last_tick_ts, reconnects, subscribed}`.

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
  real-time (or as fast as possible when `speed = 0`). Used by tests, after-hours demos,
  and Milestone 6 fault injection (it can be told to drop or delay ranges).

### 6.4 Tick bus and store
- One `asyncio` fan-out: every `Tick` goes to Candle Builder, Chain State, Paper Trade
  Manager, and Tick Store.
- Tick Store batches inserts (every 500 ms or 500 rows) into `ticks`.

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

### 6.6 Bullion (Milestone E4)
Gold and silver on their own tab, BULLION, beside the indices. Display only: no
indicator, signal or paper trade reads them, and there is no real-order path for them
either.
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
  Synthetic and replay have no bullion.
- **Not recorded.** Bullion ticks are not written to `ticks` and its candles are not stored:
  MCX trades until 23:30, and recorded evening ticks would stretch a replay and drive its
  clock past the NSE close.
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

---

## 7. Market state

### 7.1 Candle builder
- Per instrument, aggregates ticks into 1-minute OHLCV candles keyed by
  `floor(ts / 60_000)`. Volume per candle is the delta of cumulative day volume.
- On minute boundary (driven by the exchange timestamp, not wall clock, with a 2 s
  wall-clock fallback when ticks are sparse), the candle is closed, persisted to
  `candles_1m`, and `CandleClosed(key, candle)` is published.
- Gaps (no ticks in a minute) produce a carry-forward candle (O=H=L=C=prev close, V=0)
  flagged `synthetic=True`, so indicator windows stay aligned.
- VWAP is maintained on the futures stream from session open: `Σ(price×vol) / Σvol`.

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
If the feed provides IV and delta per option, they are used as-is. If not (decided in
Milestone 2), IV is computed by Black-Scholes bisection from LTP, spot, strike, time to
expiry, and a flat rate *(default 6.5%)*; delta follows from that. The source is recorded
on each `LegState` (`greeks_source = feed | computed`).

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
```

| Value | Source |
|---|---|
| Day open / high / low | today's closed spot candles plus the candle being formed; complete from 09:15 after a late start because of the candle backfill (§6.5) |
| Range position | `(spot − day_low) / (day_high − day_low)`; empty while high equals low |
| Previous close, change, change % | previous close from the feed (`cp` on the spot tick); change = spot − previous close |
| 52-week high / low | the range before today from §6.5 step 3, widened by today's high/low on every update, so a new extreme shows the moment it happens |
| Futures premium | latest futures LTP − latest spot LTP |
| India VIX and its change % | the VIX key's LTP and previous close (§6.2) |

Any value without a source is `None` and shown as "—". On the synthetic feed that is the
52-week range, previous close and VIX; on replay it is the 52-week range, and previous
close and VIX for days recorded before E1 (previous close is stored with ticks from E1 on,
once per instrument whenever it changes).

Recomputed on spot, futures and VIX ticks; cheap enough not to cache beyond the latest
value.

---

## 8. Indicators

All indicators are pure functions `f(inputs) -> IndicatorResult`:

```python
@dataclass(frozen=True)
class IndicatorResult:
    name: str
    group: Literal["trend", "oi", "premium"]
    score: float            # clamp to [-1, +1]; +bullish / −bearish
    value: dict[str, float] # raw numbers shown in the evidence table
    note: str               # one-line human reason, e.g. "EMA9 above EMA21 by 0.12%"
    quality: Literal["ok", "warming", "partial"]
```

`quality != ok` indicators are shown greyed and contribute 0 until they have enough data.

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
  below_threshold, active_exists, outside_hours, feed_down, no_price, rearm) so the signal
  card can explain an empty state.

### 9.2 Signal content

```python
class Signal:
    id, index, ts_fired, direction: BUY_CE | BUY_PE
    instrument_key, trading_symbol, strike, expiry, lot_size
    entry_price          # ATM option LTP at fire time
    target_price, stop_price
    target_basis         # "pct" | "points"
    bias, strength, breakdown
    expires_at           # ts_fired + signal_ttl_seconds
    status: active | traded | lapsed | reversed
    open_trades_on_index: list[PaperTradeBrief]   # filled when any exist
```

### 9.3 Target and stop
- **Normal day**: `target = entry × (1 + target_pct/100)`, `stop = entry × (1 + stop_pct/100)`.
- **Expiry day**: points → premium via delta at fire time:
  `target = entry + |delta| × target_points`, `stop = entry − |delta| × stop_points`,
  floored at `0.05`. `delta` from feed or computed (§7.3). Both the point and premium
  values are stored and shown.

### 9.4 Interaction with open paper trades
Open trades never block signals. When a signal fires on an index with open trades,
`open_trades_on_index` is populated (symbol, direction, entry, current P&L, minutes open)
and the frontend renders it prominently inside the signal card, regardless of whether
those trades agree or disagree with the new signal.

Independently of signals, on every `BiasComputed` the `PaperTradeManager` sets
`warning = "bias_reversed"` on each open trade whose direction opposes the new label
(CE trade with `Bearish` label, PE trade with `Bullish` label) and clears the warning when
the label no longer opposes it. Each change publishes `PaperTradeUpdated`. The warning is
informational; it never closes a trade.

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

`uv run python -m tradedisha.tools.score [--days D ...] [--params FILE]` replays recorded
days at full speed, each in a scratch database, with the given parameter file, and prints
the scorecard. The recorded database is opened read-only. Running it with the current
file and with a trial file is how a parameter change is judged.

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

## 10. Paper trading

### 10.1 Lifecycle

```
POST /paper-trades {signal_id}
  → validate signal is ACTIVE, market open, feed live (else 409 with reason)
  → open at current LTP of signal.instrument_key (not signal.entry_price)
  → slippage = fill − signal.entry_price
  → quantity = lot_size × lots
  → status OPEN; target/stop copied from signal
```

No cap on concurrent open paper trades per index or direction *(my call, follows from
"always allow")*.

On every tick for an open trade's instrument:
- `ltp ≥ target` → close `TARGET`
- `ltp ≤ stop`   → close `STOP`
- Timer: at `square_off_time` → close `SQUARE_OFF`
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
gross = (exit − entry) × quantity
net   = gross − cost_per_trade × lots
pct   = (exit − entry) / entry × 100
```
Hit = `net > 0`.

### 10.3 Journal stats
Per index and overall: trades, hits, hit rate, average win (net), average loss (net),
net total, gross total, average duration, breakdown by exit reason, count of non-`live`
fills. Computed on request from `paper_trades`; small enough not to cache.

### 10.4 Tick pruning
`POST /data/prune-ticks {until_date}` deletes rows from `ticks` with
`ts < start of (until_date + 1 day) IST`, so the chosen date is included (Anuj's decision).
Nothing else is deleted; `candles_1m`, `chain_minutes`, `bias_minutes`, `signals`, and
`paper_trades` are untouched, so replay from candles remains possible. The call first
returns a preview (`GET /data/usage?until_date=`: day count, row count, estimated MB) and
the UI requires confirmation. Deletion runs in the DB writer task in batches of 50 k rows
so the hot path is not blocked, followed by `PRAGMA incremental_vacuum`. Pruning the
current day while the feed is live is allowed; the tick store simply continues appending.
A `feed_events` row (`ticks_pruned`, with the date and row count) is written.

---

## 11. Persistence (SQLite)

WAL mode, single writer task, batched inserts. All timestamps epoch ms UTC.

| Table | Key columns | Purpose |
|---|---|---|
| `sessions` | id, token, obtained_at, expires_at | daily auth |
| `instruments` | instrument_key, symbol, exchange, type, expiry, strike, lot_size, step, loaded_on | daily master subset |
| `ticks` | key, ts, ltp, volume, oi, bid, ask, iv, delta, close_prev, bid_qty, ask_qty, bid_qty5, ask_qty5, tbq, tsq, atp, ltq | raw feed, replay source |
| `candles_1m` | key, minute_ts, o, h, l, c, v, synthetic | |
| `chain_minutes` | index, minute_ts, strike, ce_*, pe_* | per-strike per-minute chain snapshot |
| `bias_minutes` | index, minute_ts, bias, label, strength, breakdown_json | evidence history |
| `signals` | id, index, ts_fired, direction, instrument_key, entry, target, stop, basis, bias, strength, breakdown_json, status, status_ts, entry_ask, spread_pct, entry_mode, shadow, flow_score | |
| `signal_outcomes` | signal_id, end_ts, result, result_ts, best/worst price and ts, px_1m/5m/15m, spot_at_fire, spot_pre_move, spot_best_move, final | what each signal's option did next (§9.5) |
| `paper_trades` | id, signal_id, index, instrument_key, direction, qty, entry, entry_ts, slippage, target, stop, exit, exit_ts, exit_reason, exit_fill_quality, exit_price_age_ms, gross, net, warning | |
| `app_state` | key, value | schema version |
| `feed_events` | ts, kind, detail | disconnects, gaps, recentres, backfills, config reloads, tick prunes |
| `latency_samples` | ts, hop, p50, p95, p99, n | one row per hop per minute |

Indexes on `(key, ts)` for ticks and candles, `(index, minute_ts)` for chain and bias.
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
| GET | `/health` | app, db, auth state, feed health, market status |
| GET | `/auth/login` | 302 to Upstox |
| GET | `/auth/callback` | handles code, 302 to `/` |
| GET | `/instruments` | resolved spot/futures/expiry/window per index |
| GET | `/chain/{index}` | current `ChainState` snapshot + derived values |
| GET | `/stats/{index}` | `IndexStats` for the details view (§7.4) |
| GET | `/candles/{index}?minutes=375` | today's spot candles with EMA/VWAP/supertrend series |
| GET | `/bias/{index}` | latest bias + breakdown |
| GET | `/bias/{index}/history?date=` | per-minute bias for a day |
| GET | `/signals?index=&status=&date=` | signals |
| GET | `/signals/scorecard?from=&to=&index=` | how the signals of a date range turned out, per entry rule (§9.5); today by default |
| GET | `/flow` | latest order-flow reading per index (§8.5) and whether it is live or shadow |
| GET | `/signals/{id}` | one signal with breakdown and outcome |
| POST | `/paper-trades` | body `{signal_id}` → trade |
| POST | `/paper-trades/{id}/close` | manual close |
| GET | `/paper-trades?index=&date=&status=` | trades |
| GET | `/journal/stats?from=&to=` | summary stats |
| GET | `/parameters` | the config in force: version, tag, created_ts and the `ParameterSet` |
| GET | `/parameters/schema` | one entry per editable value: path, group, kind (number, integer, choice, time), limits, choices, help |
| PUT | `/parameters` | `{tag, params}`: saves a new version; 200 with it, or 422 with field errors (nothing saved) |
| GET | `/parameters/versions` | every version, newest first, with `active` on the one in force |
| GET | `/parameters/versions/{n}` | one version with its stored values; 404 if there is none |
| POST | `/parameters/versions/{n}/revert` | `{tag?}`: saves version n's values as a new version; 422 if n is unknown or already in force |
| GET | `/data/usage?until_date=` | DB size, tick rows/days total, and what a prune up to `until_date` would remove |
| POST | `/data/prune-ticks` | body `{until_date}` → deletes ticks up to and including that date; returns rows removed |
| GET | `/metrics` | latency p50/p95/p99 per hop (last 1 and 15 min), event-loop lag, queue depths |
| GET | `/config` | effective static settings (read-only, secrets redacted) |

Errors: RFC 7807 problem JSON. 409 when a paper trade is requested for a non-active
signal, outside market hours, or while the feed is not live; the `detail` says which.

### 12.2 WebSocket (`/ws`)

Server → client JSON frames `{type, ts, payload}`:

| type | cadence | payload |
|---|---|---|
| `hello` | on connect | full snapshot: health, instruments, chain per index, latest candles, bias, active signals, open trades, index stats |
| `stats` | leading-edge throttle, max 1/s per index | `IndexStats` |
| `tick` | leading-edge throttle, max 20/s per index | `{index, spot_ltp, spot_ts, fut_ltp, fut_ts}` |
| `chain` | leading-edge throttle, max 2/s per index | full window (21 rows) + derived values; small enough that diffs are not worth it |
| `candle` | per minute | closed candle + indicator series point |
| `bias` | per minute | bias + breakdown |
| `signal` | on change | full `Signal`, shadow ones included (flagged) |
| `flow` | about 1/s per index | order-flow score and its three parts (§8.5) |
| `paper_trade` | on change, and 1/s while open | trade with live P&L |
| `health` | on change | feed/auth/market status |
| `parameters` | on a save or revert | version, tag, created_ts, the set, effective-from minute |

Every frame carries `t_src` (exchange ts), `t_in` (backend ingest), `t_out` (backend send)
so the client can compute per-hop latency. Frames are serialised with orjson; one frame
may batch several events of the same type produced in the same throttle window.

Client → server: `{"type":"ping"}` only. All mutations go through REST.

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
│  │ Spot 24,512.40  Fut 24,548.10  ATM 24500  │ │ PCR 1.18   Max pain 24500   │
│  │ ▸ Details                                 │ │─────────────────────────────│
│  └───────────────────────────────────────────┘ │ OI ΔOI IV LTP │STRIKE│ LTP… │
│  ┌ MARKET VIEW ───── [–] ┐┌ SIGNAL ───── [–] ┐ │ ...                         │
│  │ Bearish ──┼──▮ Bullish││ BUY 24500 CE     │ │ ▌ 24500 ATM row highlighted │
│  │       62 Bullish      ││ @ 142.5  T 185.3 │ │ ...                         │
│  │                       ││ S 121.1    04:12 │ │                             │
│  │                       ││ [ Paper trade ]  │ │                             │
│  └───────────────────────┘└──────────────────┘ │                             │
│  ┌ PRICE CHART ───────────────────────── [–] ┐ │                             │
│  │ 1-min candles, EMA9/21, VWAP, ▲▼ markers  │ │                             │
│  └───────────────────────────────────────────┘ │                             │
│  ═══════════ drag: chart height ═════════════  │                             │
│  ┌ EVIDENCE ──────────────────────────── [–] ┐ │                             │
│  │ EMA 9/21 cross   +0.71   0.133   +0.095   │ │                             │
│  └───────────────────────────────────────────┘ │                             │
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

### 13.2 Components
- **TopBar**: market status pill (pre-open / live / closed, with clock), feed health with
  tick age colour (green < 2 s, amber < 10 s, red otherwise), auth state with Login button,
  Journal link.
- **IndexTabs**: NIFTY / BANKNIFTY, and BULLION while there is bullion data (§6.6);
  selection drives chart, meter, signal, evidence, and chain panel. A selected BULLION
  survives a reconnect, and falls back to the first index if bullion goes away.
- **BullionView** (Milestone E4, the BULLION tab, in place of the main column's panels; the
  option-chain column and its divider are not shown):
  - A card per metal, headed by the contract, expiry and lot:
    - LTP with unit, change and change %
    - Today: open, high, low with range bar, previous close, ATP
    - Liquidity: volume, OI, bid and ask with quantities, spread, buy/sell quantity and ratio
    - Contract, 1 year: high and low with distance and range bar, circuit limits
    - Next month: price, spread over near
  - The gold/silver ratio.
  - A 1-minute chart with VWAP and a GOLD / SILVER switch remembered in `localStorage`
    (`tradedisha.bullionChart`), at the index chart's height.
  - `Price`, `Group`, `Fact` and `RangeBar` are shared with IndexTiles (`components/Facts`).
- **IndexTiles**: spot, futures and ATM for the selected index, with a collapsible
  **details view** underneath showing `IndexStats` (§7.4) in five groups: day open / high
  / low with a small range bar marking the current price; 52-week high / low with the
  distance of the current price from each; previous close with change and change %;
  futures premium over spot; India VIX with its change %. Closed by default *(my call)*;
  a chevron button toggles it and the state is remembered. Missing values render as "—".
  The view follows the index tabs; VIX is the same in both.
- **Resizable layout**: two draggable dividers *(my call)* — a vertical one between the
  main column and the chain panel, and a horizontal one under the price chart setting its
  height. Each is a 4 px handle with a wider hit area, `role="separator"`, keyboard
  arrows move it, double-click resets to the default. Limits: chain panel 420–900 px and
  never more than 60% of the window; chart 200–700 px. Sizes are stored in `localStorage`
  and clamped again on load and on window resize, so a layout saved on a large screen
  cannot hide a panel on a small one. Dragging is throttled to one layout per animation
  frame. No library is added for this.
- **PanelFrame**: the frame around each of the eight dashboard panels (`tiles`, `bias`,
  `signal`, `trades`, `chart`, `evidence`, `history`, `chain`). It owns the box and a
  32 px title bar with the panel's title and one minimise / expand button; the panel
  components inside draw no box or duplicate heading of their own. Minimised, only the
  title bar is left, with a one-line summary (`lib/panelSummary.ts`: spot and change;
  strength and label; signal with entry and time left; open trades with live P&L; last
  close; bias; signals today; PCR and max pain), and the panels below move up. Contents
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
- **Panel order** (Milestone E3): the main column is six units, drawn in a remembered
  order: `tiles`, `view` (the bias meter and signal card, which share a row and move as
  one), `chart` (with its height divider), `evidence`, `trades`, `history`. Each of their
  PanelFrames has move-up and move-down buttons beside minimise; the button with nowhere
  to go is disabled, and both panels of `view` carry the same pair of buttons. The index
  tabs and the option chain do not move. The order is kept in `localStorage`
  (`tradedisha.panelOrder`); a stored list is read tolerantly (unknown and repeated ids
  dropped, missing units added at the end). "Restore panels" also resets the order and is
  shown while it differs from the default. Units are keyed, so a moved chart is not
  remounted and keeps its zoom. `lib/panels.ts` holds the order logic.
- **SidePanel** (the right-hand column holding the option-chain PanelFrame): minimising
  the chain hides the column, leaving a 28 px strip on the right edge with a "show"
  button and the panel's name; the main column takes the freed width (the chart resizes
  with it). The divider is not rendered while hidden, and the remembered width is used
  again on show. Hidden means not rendered only: the chain keeps updating in the store,
  and indicators, signals and recording are unaffected.
- **BiasMeter**: horizontal gauge −100…+100 with label and strength; animates on update.
- **PriceChart**: resizes with its container (it has no fixed height once the layout is
  resizable). `lightweight-charts` candlestick; EMA9, EMA21, VWAP line series;
  supertrend as coloured line; signal markers (▲ CE, ▼ PE) with tooltips; paper-trade
  entry/exit markers.
- **SignalCard**: direction, symbol, entry/target/stop (with points shown on expiry day),
  countdown, open-trades block when `open_trades_on_index` non-empty (each with direction,
  entry, live P&L and minutes open; closing is done from the OpenTrades panel), Paper
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
  ("Config v7 higher bar"). It opens a panel with two tabs. **Edit** is a form built from
  `/parameters/schema`, grouped as in §3.2, each field with its help text and limits; a
  changed field is outlined and shows its previous value. Saving needs a tag and at least
  one change; the server's field errors appear beside the field, its group or the tag,
  and the draft is kept. After a save the bar shows "applies from HH:MM" and the form
  starts again from the new version. **History** lists the versions, newest first, with
  the one in force marked and a Revert button on the others, which asks for a tag
  (pre-filled "Revert to vN") and a confirmation. There is no "Reload config" button.
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
- Per-index stores: `chain`, `candles` (ring buffer of 375), `bias`, `activeSignal`,
  `openTrades`, `stats`.
- Per-browser preferences in `localStorage`, read through one small hook with a
  try/catch fallback to defaults: theme (existing), `layout` (`{chainWidth, chartHeight}`),
  `panels` (which panels are minimised; replaces E1's `chainOpen`, which is read once to
  carry the choice over), `panelOrder` (the order of the main column's units) and
  `detailsOpen`.
- REST via TanStack Query for history, journal, and mutations (`POST /paper-trades`).
- Optimistic UI is not used for paper trades; the button shows a spinner until the server
  confirms, because the fill price comes from the server.

---

## 14. Time, calendar, and operating modes

- `MarketClock` provides `now()` and `status()` ∈ `pre_open | live | closed | holiday`
  from IST time and an NSE holiday list (static file for the year, editable).
- **Clock source.** `MarketClock` is injected everywhere time is read (engine, paper
  manager, square-off timer, signal TTL). In live mode it reads the wall clock. In replay
  mode it is driven by the replayed tick timestamps, so a session replayed at 21:00 still
  sees "09:15–15:30" and the engine, cut-offs, and square-off behave exactly as they did
  live. No component reads `datetime.now()` directly (enforced by a lint rule).
- Modes:
  - **live**: auth valid, market live → feed connected, engine running.
  - **standby**: market closed or holiday → no feed; UI shows last known state with a
    "Market closed" banner; replay can be started from `/api/replay` (dev only).
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
- `uvloop` event loop; `orjson` for all JSON; protobuf decode in the feed task only.
- The tick bus is in-process `asyncio` queues; consumers never block. Anything that can
  take more than ~1 ms (SQLite writes, indicator maths over full windows) runs off the hot
  path: the DB writer is a separate task with batched commits; indicators keep incremental
  state (running EMA, rolling sums) so a minute-close evaluation is O(indicators), not
  O(window).
- Chain derived values are incremental per tick (update one row's contribution to the
  sums) rather than recomputed over the window.
- WS push is throttled per channel (§12.2) on the leading edge and coalesced: a dirty
  index is pushed as soon as its minimum gap has elapsed and the latest state wins, so a
  slow client never builds a backlog. Candle, bias and parameter frames bypass the throttle
  and go out on the next pusher pass.
- Indicators recompute over the candle window (<= 400 bars) at each minute close rather
  than carrying incremental state; measured cost is microseconds and the functions stay
  pure. Revisit only if the instrument count grows by orders of magnitude. A client that falls behind by > 2 s is
  disconnected and reconnects to a fresh `hello`.
- Event-loop lag is sampled every 100 ms; if p95 lag exceeds 20 ms for a minute, a
  `feed_events` warning is written and shown in the dev overlay.
- Replay at `speed=0` is used as the load test: a full day must process in under 60 s on
  the development Mac.

### Frontend techniques
See §13.3 Performance. Additionally: WS parsing in the main thread (frames are small);
React 18 automatic batching; no state in context that changes per tick; `React.memo` on
chain rows keyed by strike; chart updates via `series.update()` not `setData()`.

### Measurement
- Every WS frame carries `t_src`, `t_in`, `t_out`; the client stamps `t_recv` and
  `t_paint` (via `requestAnimationFrame` after store commit) and posts a per-minute
  summary to `POST /api/metrics/client`.
- `/api/metrics` and the dev overlay (toggle with `?debug=1`) show per-hop p50/p95/p99.
- Per-minute summaries are stored in `latency_samples` so a slow afternoon can be
  diagnosed afterwards.

## 14b. Code quality standards

- **Python**: ruff (lint + format, strict rule set incl. `B`, `UP`, `SIM`, `PL`), mypy
  `--strict`, no `Any` in public signatures, pydantic models at every boundary (feed,
  API, DB), pure functions for all trading maths, max ~300 lines per module, docstrings on
  public functions stating units and conventions (IST vs UTC, % vs fraction).
- **TypeScript**: `strict: true`, ESLint (typescript-eslint strict + react-hooks +
  jsx-a11y), Prettier; API types generated from the backend's OpenAPI schema so DTOs
  cannot drift; no `any`.
- **Structure**: dependencies point inward: `api` → `engine`/`paper`/`market` → `store`;
  `indicators` and `engine` import nothing from `api`, `feed`, or `store`. Enforced with
  import-linter.
- **Tests**: see §15. Trading logic (indicators, engine, paper) is held at 100 % branch
  coverage; the rest at a sane level without chasing numbers.
- **Automation**: pre-commit runs ruff, mypy, ESLint, Prettier, tsc on changed files; a
  single `make check` (or `uv run check`) runs everything plus tests; a milestone is not
  "done" with it red.
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
| Integration | replay a recorded session through the full pipeline; assert persisted signals/trades match a golden file |
| API | FastAPI test client for REST contracts; WS `hello` snapshot shape |
| Frontend | component tests for SignalCard states and EvidenceTable; one Playwright smoke test against a replay backend |
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

| Item | Resolve in | Fallback |
|---|---|---|
| Exact Upstox WS protobuf schema, `full` mode fields, subscription cap | M1 | reduce `strike_window` |
| Whether IV/delta arrive on the feed | M2 | compute via Black-Scholes (§7.3) |
| Whether option-chain REST provides day OI change for opening-OI backfill | M2 | `oi_baseline=partial` flag |
| Intraday candle REST availability for same-day minutes | M3 | warm-up period with `quality=warming` |
| Indicator constants (k, bands) | M3 review point | tune on recorded days |
| 52-week high/low from daily candles matches NSE's published figures | E1 demo | show the values with their source dates on hover |
| India VIX arrives on the feed in `full` mode like the other indices | E1 demo | poll the quote API once a minute |
| `tbq`, `tsq`, `atp` and all five book levels arrive in `full` mode for index futures and the option window | S1 live day | build the trigger on whichever of them do arrive |
| Growth of the `ticks` table with the eight order-flow columns | S1 live day (Data panel) | record them only for the futures and the strikes near ATM |
| Whether order flow leads price on these contracts at all | S2 shadow scorecard | keep the minute-close rule; try enhancement 6's other options |
| MCX ticks (and the `1d` OHLC row) arrive for this account in `full` mode | E4 live check: the tab checked live by the owner, 2026-11-16 | poll the full quote once a few seconds |
