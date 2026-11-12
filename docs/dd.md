# TradeDisha — Data Dictionary

Definitions of every domain and technical term used in [intent.md](intent.md),
[plan.md](plan.md), and [spec.md](spec.md). Terms are grouped, then alphabetical within
each group. Where TradeDisha gives a term a specific meaning or value, that is stated.

---

## 1. Market and exchange terms

| Term | Meaning |
|---|---|
| **BSE** | Bombay Stock Exchange. Not used by TradeDisha v1; listed because the data provider also covers it. |
| **BANK NIFTY (NIFTY BANK)** | NSE index of the 12 most liquid banking stocks. Options on it are one of the two instruments TradeDisha covers. Strike step ₹100. Only monthly expiries since November 2024. |
| **DII** | Domestic Institutional Investors: Indian mutual funds, insurers, banks. Their net daily buying/selling is published by NSE after close. Planned v2 input, not in v1. |
| **F&O** | Futures and Options segment of NSE. |
| **FII / FPI** | Foreign Institutional (Portfolio) Investors. Their net daily buying/selling is a widely watched sentiment input. Planned v2 input, not in v1. |
| **Futures (current-month)** | A contract to buy or sell the index at a fixed price on expiry. TradeDisha subscribes to the nearest monthly future for each index and uses it (not spot) for VWAP, because spot has no traded volume. |
| **Holiday calendar** | The list of NSE trading holidays for the year. Stored as a static file; drives the `holiday` market status. |
| **Index / spot** | The live value of NIFTY 50 or NIFTY BANK itself, computed by NSE from constituent stocks. "Spot" is this value, as opposed to futures or option prices. |
| **IST** | Indian Standard Time (UTC+5:30). All user-facing times and all trading-hour rules are in IST. Stored timestamps are UTC epoch milliseconds. |
| **Lot / lot size** | The minimum tradable quantity of an F&O contract, set by NSE (for example 75 for NIFTY, 30 for BANK NIFTY; these change). Read from the instrument master. Paper trades are one lot. |
| **Market hours** | 09:15 to 15:30 IST on trading days. |
| **Market status** | One of `pre_open`, `live`, `closed`, `holiday`, derived from IST time and the holiday calendar. |
| **NIFTY (NIFTY 50)** | NSE's benchmark index of 50 large-cap stocks. Strike step ₹50. Weekly expiries. |
| **NSE** | National Stock Exchange of India, where NIFTY and BANK NIFTY derivatives trade. |
| **Pre-open** | 09:00 to 09:15 IST, when NSE runs its opening auction. TradeDisha shows status but does not evaluate signals. |
| **Square-off** | Closing an intraday position before the session ends. TradeDisha squares off open paper trades at 15:15 IST (default). |
| **Tick** | One price/volume/OI update for one instrument from the exchange feed. The smallest unit of market data in the system. |
| **Tick size** | The minimum price increment of an instrument (₹0.05 for index options). |
| **Trading day / session** | One NSE trading day from 09:15 to 15:30. "Session open" values (opening OI, VWAP start) reset each day. |

---

## 2. Options terms

| Term | Meaning |
|---|---|
| **ATM (at the money)** | The strike closest to the current spot. TradeDisha: `round(spot / step) × step`. Signals always name the ATM option at fire time. |
| **Black-Scholes** | The standard formula for pricing an option from spot, strike, time to expiry, rate, and volatility. TradeDisha uses it in reverse (bisection) to compute IV from a traded premium when the feed does not supply IV. |
| **Build-up (OI classification)** | Reading the combination of price change and OI change for one option over one minute: long build-up (price ↑, OI ↑), short build-up (price ↓, OI ↑), short covering (price ↑, OI ↓), long unwinding (price ↓, OI ↓). |
| **Call option (CE)** | The right to buy the index at the strike on expiry. Gains when the index rises. "CE" is NSE's suffix for calls. A bullish signal recommends buying a CE. |
| **Delta** | How much an option's premium moves for a ₹1 move in the index, between 0 and 1 (calls) or 0 and −1 (puts). Used on expiry day to convert index-point targets into premium targets. |
| **Expiry** | The date an option contract ceases to exist. NIFTY: weekly (NSE's weekly expiry weekday has changed before and may again; the app reads actual expiry dates from the instrument master and never assumes a weekday). BANK NIFTY: monthly. TradeDisha trades the nearest expiry, including the expiring contract on expiry day itself. |
| **Expiry day** | A trading day on which the subscribed options expire. Premiums decay fast and OI readings distort. TradeDisha switches to expiry-day mode (points-based targets, 13:00 cut-off, halved OI weight). |
| **Greeks** | Collective name for option sensitivities (delta, gamma, theta, vega). TradeDisha uses delta and IV only. |
| **ITM / OTM (in / out of the money)** | A call is ITM if strike < spot, OTM if strike > spot; reversed for puts. Used only for display context. |
| **IV (implied volatility)** | The volatility figure that makes the Black-Scholes price equal the traded premium, expressed as an annualised percentage. Rising IV means the market expects bigger moves. A premium-behaviour input. |
| **Max pain** | The strike at which option buyers, in aggregate, lose the most (equivalently, option writers gain the most) if the index expires there. Computed over the subscribed strike window. Its drift over time is an OI-structure input. |
| **OI (open interest)** | The number of outstanding contracts for one option. Rising OI means new positions being opened; falling means positions being closed. |
| **OI change** | Difference in OI vs a reference: "since open" (vs the first OI of the session) and "since previous minute". |
| **Opening OI** | OI at session start for each option. Baseline for "OI change since open". Backfilled from the broker's option-chain snapshot when the app starts late; flagged `partial` if the baseline could not be recovered. |
| **Option chain** | The table of all strikes for one expiry, with call data on the left and put data on the right of the strike column. TradeDisha shows ATM ± 10 strikes. |
| **PCR (put-call ratio)** | Total put OI divided by total call OI over ATM ± 5 strikes. Above 1 is read as bullish (put writers are confident), below 1 as bearish. |
| **Premium** | The traded price of an option. "Entry price", "target", and "stop" in a signal are premium values. |
| **Put option (PE)** | The right to sell the index at the strike on expiry. Gains when the index falls. "PE" is NSE's suffix for puts. A bearish signal recommends buying a PE. |
| **Strike** | The index level at which an option can be exercised. Strikes exist at fixed steps (₹50 NIFTY, ₹100 BANK NIFTY). |
| **Strike step** | The spacing between adjacent strikes for an index. Inferred from the instrument master. |
| **Strike window** | The set of strikes TradeDisha subscribes to and computes over: ATM ± `strike_window` (default 10). |
| **Theta / time decay** | The loss of option premium purely from the passage of time. Steepest on expiry day; the reason for expiry-day mode. |
| **Writer (option seller)** | A participant who sells options and collects premium. OI rising on puts is read as writers confident the index will not fall, hence bullish. |

---

## 3. Technical-analysis and signal terms

| Term | Meaning |
|---|---|
| **Aggregator** | The function that combines group scores with their weights into one bias value. |
| **Bias** | TradeDisha's overall view of one index: a number in [−1, +1], negative bearish, positive bullish. Recomputed every minute. |
| **Bias label** | `Bullish` if bias ≥ `neutral_band`, `Bearish` if bias ≤ −`neutral_band`, else `Neutral`. Default band 0.20. |
| **Candle (1-minute)** | Open, high, low, close, and volume of an instrument over one minute. Built from ticks; the unit on which indicators run. |
| **Contribution** | An indicator's score × its effective weight: its share of the bias. Shown in the evidence table. |
| **Divergence** | Spot moves one way but premiums do not confirm (for example spot up, calls flat). Scored negatively by `premium_confirmation`. |
| **EMA (exponential moving average)** | A moving average that weights recent prices more. TradeDisha uses EMA 9 and EMA 21 of 1-minute spot closes. |
| **EMA crossover** | EMA 9 above EMA 21 is read as bullish, below as bearish; the gap size sets strength. |
| **Entry threshold** | The absolute bias value at which a signal fires. Default 0.50. |
| **Evidence / breakdown** | The structured list of every indicator's score, weight, contribution, raw values, and one-line note that accompanies each bias and signal. The explainability payload. |
| **Group** | One of the three families of indicators: `trend`, `oi`, `premium`. Each has a weight; indicators within a group split that weight equally. |
| **Hysteresis (re-arm)** | Optional gate, off by default (`rearm_hysteresis = 0`). If set, a new signal in the same direction as the one that just ended needs bias to fall below `entry_threshold − rearm_hysteresis` and re-cross. With it off, a fresh signal fires at the next minute close whenever bias is beyond threshold and no signal is active. |
| **Indicator** | A pure function from candles and/or chain state to an `IndicatorResult` (score, raw values, note, quality). Nine in v1. |
| **Lapse** | A signal that was not paper-traded within its time-to-live (default 5 minutes). |
| **Momentum / ROC (rate of change)** | Percentage change of a value over N minutes. Used for ATM call vs put premium momentum (5 minutes). |
| **Neutral band** | Absolute bias below which the label is `Neutral`. Default 0.20. |
| **Points** | Index points, the unit of index movement (NIFTY 24,500 → 24,540 is 40 points). Expiry-day targets and stops are set in points. |
| **Premium confirmation** | Whether call/put premium changes agree with the spot move over the last 5 minutes. |
| **Quality (indicator)** | `ok`, `warming` (not enough history yet), or `partial` (baseline uncertain, for example opening OI). Non-`ok` indicators show greyed and contribute 0. |
| **Reversal** | Bias changes sign, or falls inside the neutral band, while a signal is active. Ends the signal. Also flags opposing open paper trades with "bias reversed". |
| **Score** | An indicator's output in [−1, +1]. |
| **Signal / recommendation** | A concrete trade suggestion: index, option (strike, expiry, CE/PE), entry premium, target, stop, time, evidence. Fires at a minute close when |bias| ≥ entry threshold, no signal is active on that index, it is within signal hours, and the feed is live. Open paper trades never block it. |
| **Signal status** | `active` (shown, can be paper-traded), `traded` (a paper trade was opened from it), `lapsed`, `reversed`. |
| **Signal TTL** | Time-to-live: how long a signal stays active untraded. Default 300 seconds. |
| **Stop (stop-loss)** | Premium level at which a trade is closed at a loss. Default entry × (1 − 15 %). Expiry day: entry − |delta| × stop points. |
| **Strength** | `round(|bias| × 100)`, shown 0–100 on the meter. |
| **Supertrend** | A trend-following indicator built from average true range (period 10, multiplier 3). Price above the line is bullish, below is bearish. |
| **Target** | Premium level at which a trade is closed at a profit. Default entry × (1 + 30 %). Expiry day: entry + |delta| × target points. |
| **Trend (price trend)** | The indicator group reading direction and momentum of the index: EMA crossover, VWAP position, supertrend. |
| **VWAP (volume-weighted average price)** | Σ(price × volume) / Σ volume from session open, on the futures contract. Price above VWAP is bullish. |
| **Weight** | The share of the bias assigned to a group. Defaults: trend 0.40, OI 0.35, premium 0.25. On expiry day the OI weight is halved and redistributed. |

---

## 4. Paper trading and journal terms

| Term | Meaning |
|---|---|
| **Cost per trade** | A flat amount deducted per round trip per lot to approximate brokerage, STT, exchange charges, and GST. Default ₹60. Configurable. |
| **Exit reason** | Why a paper trade closed: `TARGET`, `STOP`, `SQUARE_OFF`, `MANUAL`. |
| **Fill** | The price at which a paper trade is recorded as opened or closed. Entry fill is the LTP at the moment of the click (a live feed is required); exit fill is the LTP that triggered the exit. |
| **Fill quality** | How trustworthy an exit price is: `live` (feed healthy), `after_gap` (first tick after a feed outage triggered the exit, so the price may have jumped past target or stop), `stale` (square-off fired while the feed was down; the last price seen was used, with its age recorded). Anything other than `live` is badged in the journal. |
| **Gross P&L** | (exit − entry) × quantity, before costs. |
| **Hit / hit rate** | A trade is a hit if net P&L > 0. Hit rate is hits ÷ trades. |
| **Journal** | The list of all paper trades with their outcomes, plus summary statistics. |
| **Net P&L** | Gross P&L minus cost per trade. The figure hit rate and summaries are based on. |
| **Open trade** | A paper trade not yet closed. Tracked tick by tick for target/stop. |
| **Paper trade** | A simulated trade opened by the trader clicking "Paper trade" on an active signal. Never placed with the broker. |
| **Quantity** | Lot size × lots (default 1 lot). |
| **Slippage** | Entry fill minus the signal's entry price: how far the price moved between the signal firing and the click. Recorded per trade. |
| **Square-off time** | When all open paper trades are force-closed. Default 15:15 IST. |
| **Warning (bias reversed)** | A flag on an open paper trade whose direction opposes the current bias label (a CE trade while Bearish, a PE trade while Bullish). Set and cleared every minute as the label changes. Informational; does not close the trade. |

---

## 5. Data-provider and feed terms

| Term | Meaning |
|---|---|
| **Access token** | The credential Upstox issues after login, valid until about 03:30 IST the next day. Stored in `sessions`. |
| **Angel One SmartAPI** | A free broker API; the fallback market-data provider if Upstox proves unsuitable. |
| **API key / secret / redirect URI** | Credentials obtained by registering an application in the Upstox developer console. Held in `.env`. |
| **Auth state** | `missing`, `valid`, or `expired`. Drives whether the feed connects and what the top bar shows. |
| **Backfill** | Fetching the part of today's data that was missed because the app started after market open: 1-minute candles and the option-chain snapshot. |
| **Backoff (exponential)** | Waiting progressively longer between reconnect attempts: 1 s, 2 s, 4 s … up to 30 s. |
| **Feed** | The continuous stream of ticks from the broker's websocket. |
| **Feed health** | `connecting`, `connected`, or `disconnected`, plus last-tick timestamp, reconnect count, and subscribed instrument count. |
| **Full mode** | The Upstox websocket subscription level that includes depth, OI, and Greeks, as opposed to LTP-only. |
| **Instrument key** | Upstox's unique identifier for one tradable instrument (for example `NSE_INDEX|Nifty 50`, `NSE_FO|12345`). Primary key for ticks and candles. |
| **Instrument master** | The daily file from Upstox listing every tradable instrument with symbol, expiry, strike, type, lot size, tick size. |
| **LTP (last traded price)** | The most recent trade price of an instrument. |
| **Market data provider** | The interface every feed implementation satisfies: connect, subscribe, unsubscribe, stream ticks, report health. Implementations: Upstox, replay, synthetic (tests). |
| **OAuth** | The login flow in which the trader authorises TradeDisha in Upstox's web page and Upstox redirects back with a code that is exchanged for an access token. |
| **Protobuf** | Protocol Buffers, the binary encoding Upstox uses for websocket market data. |
| **Re-centre** | Moving the strike window when ATM has shifted by `recenter_strikes` (default 2): subscribe new strikes, unsubscribe old ones, fetch baselines for the new ones. |
| **Replay** | Feeding recorded ticks back through the system at real or accelerated speed. Used for tests, after-hours demos, load testing, and fault injection. |
| **Session** | (Auth sense) one day's login record. See also "trading day / session" in §1. |
| **Subscription** | Telling the websocket which instrument keys to stream. Subject to a provider-set cap on count. |
| **Synthetic candle** | A carry-forward candle created for a minute with no ticks (O=H=L=C=previous close, volume 0) so indicator windows stay aligned. |
| **Upstox** | The Indian broker whose free API v2 is TradeDisha's chosen market-data provider. |
| **Websocket** | A persistent two-way connection. Used broker → backend (market data) and backend → browser (live updates). |

---

## 6. Architecture and software terms

| Term | Meaning |
|---|---|
| **Adapter** | A class that translates an external system's interface (Upstox) into TradeDisha's internal one (`MarketDataProvider`). |
| **asyncio** | Python's built-in framework for cooperative, single-threaded concurrency. The backend is an asyncio application. |
| **Batched insert** | Writing many rows in one database transaction (every 500 ms or 500 rows) instead of one at a time. |
| **Candle builder** | The component that turns ticks into 1-minute candles and emits a `CandleClosed` event on each minute boundary. |
| **Chain state** | The in-memory option chain for one index, with derived values (ATM, PCR, OI changes, max pain) kept up to date per tick. |
| **Coalescing** | When several updates arrive within one throttle window, sending only the latest state rather than every intermediate one. |
| **Degraded mode** | Market is live but auth is missing/expired or the feed is disconnected. Last-known data is shown greyed; bias still computed but greyed; no new signals; paper-trade entry and manual close refused; target/stop checked again from the first tick after the feed returns (`after_gap`); the square-off timer still fires at the last known price (`stale`). |
| **DTO (data transfer object)** | A typed structure that defines the shape of data crossing a boundary (API request/response, websocket frame). Generated into TypeScript from the backend's OpenAPI schema. |
| **Event bus** | The in-process publish/subscribe mechanism through which components announce `CandleClosed`, `BiasComputed`, `SignalFired`, `PaperTradeUpdated`, etc. |
| **Event-loop lag** | How late asyncio runs a task compared to when it was due. Sampled every 100 ms; a sign the hot path is blocked. |
| **FastAPI** | The Python web framework used for REST and websocket endpoints. |
| **Fan-out** | Delivering each tick to several consumers (candle builder, chain state, paper manager, tick store) concurrently. |
| **Fault injection** | Deliberately dropping or delaying replayed ticks to test reconnect and degraded-mode behaviour. |
| **Frame (websocket)** | One JSON message from backend to browser: `{type, ts, t_src, t_in, t_out, payload}`. |
| **`hello` frame** | The first websocket frame after connect, containing a full snapshot of current state so the client needs no event replay. |
| **Hop** | One leg of the data path used for latency measurement: exchange → ingest, ingest → sent, sent → received, received → painted. |
| **Hot path** | The code executed for every tick. Must never block; anything slow is moved off it. |
| **Hypothesis** | A Python property-based testing library; used to assert indicator scores stay within bounds for any input. |
| **Import-linter** | A tool that enforces which Python packages may import which, keeping dependencies pointing inward. |
| **Incremental computation** | Updating a running value (EMA, rolling sum, chain totals) from the latest input rather than recomputing over the whole window. |
| **Ingest timestamp (`t_in`)** | When the backend received a tick. Start of the latency budget TradeDisha controls. |
| **Latency budget** | Agreed maximum time per hop at the 95th percentile, measured from arrival at the app (not from the exchange timestamp; the broker→app hop is shown separately). Total ingest → painted under 250 ms; minute close detected → signal painted under 100 ms. |
| **lightweight-charts** | TradingView's open-source canvas charting library, used for the candlestick chart. |
| **Market clock** | The single source of "what time is it and what is the market status?" for the whole backend. Reads the wall clock in live mode and the replayed tick timestamps in replay mode, so replays behave exactly as the live session did. No other code reads the system clock directly. |
| **Minute close detected** | The moment the candle builder closes a 1-minute candle: the first tick of the next minute, or a 2-second wall-clock fallback when ticks are sparse. The 100 ms signal latency budget starts here; the detection delay itself is reported separately. |
| **Migration** | A versioned SQL script that changes the database schema; applied in order at startup. |
| **mypy (strict)** | Python static type checker run with all strictness flags. |
| **orjson** | A fast JSON library used for all serialisation. |
| **p50 / p95 / p99** | Percentiles: the value below which 50 %, 95 %, 99 % of samples fall. Latency targets are stated at p95. |
| **Parameter set** | The validated, typed in-memory form of `config/params.toml`: every tunable value that shapes a signal. |
| **Pre-commit** | Git hook runner that executes linters and type checks on changed files before each commit. |
| **Prune (ticks)** | Deleting raw tick rows up to and including a date the trader chooses, from the Data panel, after a preview and confirmation. Candles, chain minutes, bias, signals, and paper trades are never pruned. Nothing is pruned automatically. |
| **Pure function** | A function whose output depends only on its inputs and which has no side effects. All indicator and signal maths is written this way so it is trivially testable. |
| **Pydantic** | Python library for typed, validated data models; used for settings, the parameter set, DTOs, and boundary objects. |
| **Reload (config)** | Re-reading `config/params.toml` on request; applied at the next minute close if valid, rejected with field errors if not. |
| **Repository (data access)** | A thin module that owns the SQL for one table or aggregate. |
| **REST** | The HTTP request/response API (`/api/...`) used for snapshots, history, and all mutations. |
| **ruff** | Python linter and formatter. |
| **SQLAlchemy Core** | The SQL-expression layer (not the ORM) used to talk to SQLite. |
| **SQLite (WAL mode)** | The embedded database file holding all persisted data. Write-Ahead Logging mode lets reads proceed while the writer task commits. |
| **Standby mode** | Market closed or holiday: no feed, last-known state shown with a "Market closed" banner. |
| **Static settings** | Values that need a restart and are not about the algorithm (credentials, paths, indices, market hours). From `.env`. Distinct from the parameter set. |
| **Store (frontend)** | A client-side state container (Zustand) holding live data per index; updated from websocket frames and rendered once per animation frame. |
| **TanStack Query / Virtual** | React libraries for server-state fetching/caching and for rendering only the visible rows of a long table. |
| **Throttle window** | The minimum interval between pushes on one websocket channel (for example 250 ms for ticks, 500 ms for chain). |
| **Tick bus** | The asyncio queue structure that fans each tick out to consumers. |
| **Tick store** | The component that batches ticks into the `ticks` table. |
| **uv** | The Python package and environment manager used for the backend. No pip, poetry, or conda. |
| **uvicorn / uvloop** | The ASGI server that runs FastAPI, and the faster event-loop implementation it is configured to use. |
| **Vite** | The frontend build tool and dev server. |
| **Zustand** | A small React state-management library used for the live per-index stores. |

---

## 7. Database tables (quick reference)

| Table | One row is |
|---|---|
| `sessions` | one Upstox login (token, obtained, expires) |
| `instruments` | one tradable instrument from the daily master subset |
| `ticks` | one tick for one instrument |
| `candles_1m` | one 1-minute candle for one instrument |
| `chain_minutes` | one strike of one index at one minute close (CE and PE values) |
| `bias_minutes` | one index's bias and evidence at one minute close |
| `signals` | one signal with its evidence and final status |
| `paper_trades` | one paper trade from open to close, including exit fill quality |
| `app_state` | one key/value (schema version) |
| `feed_events` | one operational event (disconnect, gap, re-centre, backfill, config reload) |
| `latency_samples` | one hop's latency percentiles for one minute |

---

## 8. Abbreviations

| Abbrev. | Expansion |
|---|---|
| ATM | at the money |
| ATR | average true range (used inside supertrend) |
| CE / PE | call European / put European (NSE option suffixes) |
| DII | Domestic Institutional Investors |
| EMA | exponential moving average |
| F&O | futures and options |
| FII | Foreign Institutional Investors |
| GST | Goods and Services Tax (on brokerage) |
| IST | Indian Standard Time |
| ITM / OTM | in / out of the money |
| IV | implied volatility |
| LTP | last traded price |
| NSE / BSE | National / Bombay Stock Exchange |
| OHLCV | open, high, low, close, volume |
| OI | open interest |
| P&L | profit and loss |
| PCR | put-call ratio |
| ROC | rate of change |
| STT | Securities Transaction Tax |
| TTL | time to live |
| VWAP | volume-weighted average price |
| WS | websocket |
