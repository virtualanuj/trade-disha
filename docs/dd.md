# TradeDisha — Data Dictionary

Definitions of every domain and technical term used in [intent.md](intent.md),
[plan.md](plan.md), [spec.md](spec.md), [signal.md](signal.md) and
[enhancements.md](enhancements.md). Terms are grouped, then alphabetical within each group
(ignoring case and punctuation). Where TradeDisha gives a term a specific meaning or
value, that is stated. Index (NIFTY, BANK NIFTY) values are given first; where bullion
differs, its value follows or is in §1a.

---

## 1. Market and exchange terms

| Term | Meaning |
|---|---|
| **BANK NIFTY (NIFTY BANK)** | NSE index of the 12 most liquid banking stocks. Options on it are one of the two instruments TradeDisha covers. Strike step ₹100. Only monthly expiries since November 2024. |
| **BSE** | Bombay Stock Exchange. Not used by TradeDisha v1; listed because the data provider also covers it. |
| **DII** | Domestic Institutional Investors: Indian mutual funds, insurers, banks. Their net daily buying/selling is published by NSE after close. Planned v2 input, not in v1. |
| **FII / FPI** | Foreign Institutional (Portfolio) Investors. Their net daily buying/selling is a widely watched sentiment input. Planned v2 input, not in v1. |
| **F&O** | Futures and Options segment of NSE. |
| **Futures (current-month)** | A contract to buy or sell the index at a fixed price on expiry. TradeDisha subscribes to the nearest monthly future for each index and uses it (not spot) for VWAP, because spot has no traded volume. |
| **Holiday calendar** | The list of NSE trading holidays for the year, in `config/nse-holidays.txt`; drives the `holiday` market status. MCX keeps its own calendar (§1a). |
| **Index / spot** | The live value of NIFTY 50 or NIFTY BANK itself, computed by NSE from constituent stocks. "Spot" is this value, as opposed to futures or option prices. |
| **IST** | Indian Standard Time (UTC+5:30). All user-facing times and all trading-hour rules are in IST. Stored timestamps are UTC epoch milliseconds. |
| **Lot / lot size** | The minimum tradable quantity of an F&O contract, set by NSE (for example 75 for NIFTY, 30 for BANK NIFTY; these change). Read from the instrument master. Paper trades are one lot. |
| **Market hours** | NSE: 09:15 to 15:30 IST on trading days. MCX bullion trades longer hours (§1a). |
| **Market status** | One of `pre_open`, `live`, `closed`, `holiday`, derived from IST time and the holiday calendar. Means the NSE session unless stated; the BULLION tab shows the MCX status instead. |
| **NIFTY (NIFTY 50)** | NSE's benchmark index of 50 large-cap stocks. Strike step ₹50. Weekly expiries. |
| **NSE** | National Stock Exchange of India, where NIFTY and BANK NIFTY derivatives trade. |
| **Pre-open** | 09:00 to 09:15 IST, when NSE runs its opening auction. TradeDisha shows status but does not evaluate signals. |
| **Square-off** | Closing an intraday position before the session ends. TradeDisha squares off open index paper trades at 15:15 IST and bullion ones at 23:00 (defaults). |
| **Tick** | One price/volume/OI update for one instrument from the exchange feed. The smallest unit of market data in the system. |
| **Tick size** | The minimum price increment of an instrument (₹0.05 for index options). |
| **Trading day / session** | One NSE trading day from 09:15 to 15:30. "Session open" values (opening OI, VWAP start) reset each day. |

---

## 1a. Bullion and MCX terms

Bullion has its own trend bias, signals and paper trades (spec §9a), apart from the index
ones: nothing of bullion feeds the index market view or recommendations.

| Term | Meaning |
|---|---|
| **ATP (average traded price)** | The exchange's own volume-weighted average price for the day, sent with each full-mode tick. Shown as "ATP (VWAP)" on the metal card. |
| **Bullion** | Gold and silver. In TradeDisha, the MCX `GOLD` and `SILVER` futures shown on the BULLION tab. Upstox has no spot price for either, so the near-month future stands in for it. |
| **Bullion bias** | The trend-only bias of one metal: EMA cross, VWAP position and supertrend on its near-month 1-minute candles, the trend group carrying the whole weight. Worked out `eval_offset_seconds` after each minute close. |
| **Bullion gap** | An MCX outage while MCX is open: no bullion tick for `bullion_live_max_tick_age_ms` (15 s). Logged to `feed_events` as `bullion_gap_start` / `bullion_gap_end`. While it lasts the bullion status is `stale`, so bullion signals and paper-trade entry pause; the index side is unaffected. |
| **Bullion signal** | A recommendation to buy or sell a metal's near-month future, fired when its bullion bias reaches `bullion.entry_threshold` within the bullion signal hours (09:15–22:45). Target and stop are a % of the price. Paper only. |
| **Bullion status** | `live`, `stale`, `closed` or `holiday`: MCX status combined with how fresh the last bullion tick is. `stale` means MCX is open but no bullion tick has arrived recently. Sent in the health response; drives the BULLION tab's banner and top-bar pills, and only `live` lets bullion signals fire and paper trades open or close. |
| **BUY_FUT / SELL_FUT** | A bullion signal's direction: buy (long) or sell (short) the near-month future. A short gains when the price falls; its target is below the entry and its stop above. |
| **Buy / sell quantity** | Total buy quantity (TBQ) and total sell quantity (TSQ): all buy and sell orders pending on the exchange for the contract. The **buy/sell ratio** is TBQ ÷ TSQ; above 1 means more waiting to buy than to sell. |
| **Calendar spread** | Next-month price minus near-month price, also shown as a % of the near price. Normally positive (contango), reflecting the cost of carry. |
| **Circuit limits** | The upper and lower prices the exchange allows the contract to trade at today. From the full quote at start. |
| **Contract one-year range** | The contract's highest high and lowest low over a year of daily candles up to yesterday, widened by today's range. Days with no volume are skipped (see Placeholder price). |
| **CTT (Commodity Transaction Tax)** | The tax on commodity futures sales on MCX (0.01 % of the sell value). Part of the bullion paper-trade cost's `cost_pct_of_value`. |
| **Day range position** | Where the price sits in today's range: 0 at the day's low, 1 at the high. Drawn as a marker on the range bar. |
| **Delivery period** | The last days of an MCX contract, when open positions settle by physical delivery. TradeDisha rolls to the next contract on expiry day so it never shows a contract in delivery. |
| **Evening session / late open** | A day when MCX shuts its morning session but trades in the evening, often on an NSE holiday. Written as `YYYY-MM-DD HH:MM` in the MCX calendar; MCX status is `closed` until that time. |
| **Gold (MCX `GOLD`)** | The 1 kg gold futures contract, quoted in ₹ per 10 g. |
| **Gold/silver ratio** | How many kilograms of silver one kilogram of gold buys: gold × 100 ÷ silver (gold is quoted per 10 g, silver per kg). A widely watched gauge of whether gold or silver is relatively expensive. |
| **MCX** | Multi Commodity Exchange of India, where gold and silver futures trade. A different exchange from NSE, with its own hours and holidays. |
| **MCX holiday calendar** | `config/mcx-holidays.txt`: `YYYY-MM-DD` for a day closed throughout, `YYYY-MM-DD HH:MM` for an evening-only day. Maintained by hand from the MCX circular. |
| **MCX hours** | 09:00 to 23:30 IST, extended to 23:55 while the US is on standard time (roughly November to March). Settings `mcx_open` and `mcx_close`; the close is changed by hand with the season. |
| **Mini / petal contracts** | Smaller gold and silver contracts (`GOLDM`, `GOLDPETAL`, `SILVERM` and others). Excluded: only the full-size `GOLD` and `SILVER` contracts are shown. |
| **Near / next month** | The near contract is the one with the nearest expiry strictly after today; the next is the one after it. Prices and charts are for the near contract; the next contract's price is shown for the calendar spread. |
| **Placeholder price** | A made-up price on the daily candles of a future's early days, before it trades (one gold contract showed ₹2,47,917). Recognised by zero volume and skipped. |
| **Point value / qty multiplier** | Rupees gained or lost per one-point price move, per lot: the MCX file's `qty_multiplier` (GOLD 100: priced per 10 g on a 1 kg lot; SILVER 30). Stored as a bullion signal's `lot_size`; paper P&L = side × move × point value × lots. |
| **Previous close (bullion)** | Yesterday's settlement price. From the feed's `cp` field; before the first tick it is worked out from the full quote as last price − net change. |
| **Roll** | Switching from the expiring contract to the next one. Bullion rolls on expiry day. |
| **Silver (MCX `SILVER`)** | The 30 kg silver futures contract, quoted in ₹ per kg. |

---

## 2. Options terms

| Term | Meaning |
|---|---|
| **ATM (at the money)** | The strike closest to the current spot. TradeDisha's "ATM" is the option chain's centre strike, which only moves (re-centres) once spot is `recenter_strikes` (2) strikes away, so it can be up to about two strikes from the true nearest. Indicators and signals both use it. |
| **Black-Scholes** | The standard formula for pricing an option from spot, strike, time to expiry, rate, and volatility. TradeDisha uses it only to compute **delta** when the feed sends none (expiry-day targets, live levels), with the option's IV from the feed or 15 % if unknown. It does not solve for IV. |
| **Build-up (OI classification)** | Reading the combination of price change and OI change for one option over one minute: long build-up (price ↑, OI ↑), short build-up (price ↓, OI ↑), short covering (price ↑, OI ↓), long unwinding (price ↓, OI ↓). |
| **Call option (CE)** | The right to buy the index at the strike on expiry. Gains when the index rises. "CE" is NSE's suffix for calls. A bullish signal recommends buying a CE. |
| **Delta** | How much an option's premium moves for a ₹1 move in the index, between 0 and 1 (calls) or 0 and −1 (puts). Used on expiry day to convert index-point targets into premium targets. |
| **Expiry** | The date an option contract ceases to exist. NIFTY: weekly (NSE's weekly expiry weekday has changed before and may again; the app reads actual expiry dates from the instrument master and never assumes a weekday). BANK NIFTY: monthly. TradeDisha trades the nearest expiry, including the expiring contract on expiry day itself. |
| **Expiry day** | A trading day on which the subscribed options expire. Premiums decay fast and OI readings distort. TradeDisha switches to expiry-day mode (points-based targets, 13:00 cut-off, halved OI weight). |
| **Greeks** | Collective name for option sensitivities (delta, gamma, theta, vega). TradeDisha uses delta and IV only. |
| **ITM / OTM (in / out of the money)** | A call is ITM if strike < spot, OTM if strike > spot; reversed for puts. Used only for display context. |
| **IV (implied volatility)** | The volatility figure that makes the Black-Scholes price equal the traded premium, expressed as an annualised percentage. Rising IV means the market expects bigger moves. A premium-behaviour input. |
| **Max pain** | The strike at which option buyers, in aggregate, lose the most (equivalently, option writers gain the most) if the index expires there. Computed over the subscribed strike window. Its drift over time is an OI-structure input. |
| **OI change** | Difference in OI vs a reference: "since open" (vs the first OI of the session) and "since previous minute". |
| **OI (open interest)** | The number of outstanding contracts for one option. Rising OI means new positions being opened; falling means positions being closed. |
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
| **Aggressor side** | Which side initiated a trade by accepting the other's price: the buyer (paying the ask) or the seller (hitting the bid). |
| **Bias** | TradeDisha's overall view of one index: a number in [−1, +1], negative bearish, positive bullish. Recomputed every minute. |
| **Bias label** | `Bullish` if bias ≥ `neutral_band`, `Bearish` if bias ≤ −`neutral_band`, else `Neutral`. Default band 0.20. |
| **Candle (1-minute)** | Open, high, low, close, and volume of an instrument over one minute. Built from ticks; the unit on which indicators run. |
| **Contribution** | An indicator's score × its effective weight: its share of the bias. Shown in the evidence table. |
| **Divergence** | Spot moves one way but premiums do not confirm (for example spot up, calls flat). Scored negatively by `premium_confirmation`. |
| **EMA crossover** | EMA 9 above EMA 21 is read as bullish, below as bearish; the gap size sets strength. |
| **EMA (exponential moving average)** | A moving average that weights recent prices more. TradeDisha uses EMA 9 and EMA 21 of 1-minute spot closes. |
| **Entry threshold** | The absolute bias value at which a signal fires. Default 0.50 for the indices, 0.60 for bullion (`bullion.entry_threshold`). |
| **Evidence / breakdown** | The structured list of every indicator's score, weight, contribution, raw values, and one-line note that accompanies each bias and signal. The explainability payload. |
| **Fired / live levels** | A signal's entry, target and stop as it fired (stored, never changed) and the same rule applied to the price now (shown while it waits). A paper trade takes the live levels at its fill. |
| **Group** | One of the three families of indicators: `trend`, `oi`, `premium`. Each has a weight; indicators within a group split that weight equally. |
| **Hysteresis (re-arm)** | Optional gate, off by default (`rearm_hysteresis = 0`). If set, a new signal in the same direction as the one that just ended needs bias to fall below `entry_threshold − rearm_hysteresis` and re-cross. With it off, a fresh signal fires at the next minute close whenever bias is beyond threshold and no signal is active. |
| **Indicator** | A pure function from candles and/or chain state to an `IndicatorResult` (score, raw values, note, quality). Nine in v1. |
| **Lapse** | A signal that was not paper-traded within its time-to-live (default 5 minutes). |
| **Momentum / ROC (rate of change)** | Percentage change of a value over N minutes. Used for ATM call vs put premium momentum (5 minutes). |
| **Net volume** | Buyer-initiated minus seller-initiated traded volume in one minute, worked out from the ticks (Upstox does not supply it): see Quote rule and Tick rule. Shown as a histogram under the price chart, from the near-month future (an index has no volume). Display only. |
| **Neutral band** | Absolute bias below which the label is `Neutral`. Default 0.20. |
| **Points** | Index points, the unit of index movement (NIFTY 24,500 → 24,540 is 40 points). Expiry-day targets and stops are set in points. |
| **Premium confirmation** | Whether call/put premium changes agree with the spot move over the last 5 minutes. |
| **Quality (indicator)** | `ok`, `warming` (not enough history yet), or `partial` (baseline uncertain, for example opening OI). Non-`ok` indicators show greyed and contribute 0. |
| **Quote rule** | Signing a trade by where it printed against the quote standing before it: at or above the ask, a buy; at or below the bid, a sell. |
| **Reversal** | Bias changes sign, or falls inside the neutral band, while a signal is active. Ends the signal. Also flags opposing open paper trades with "bias reversed". |
| **Score** | An indicator's output in [−1, +1]. |
| **Signal / recommendation** | A concrete trade suggestion: index, option (strike, expiry, CE/PE), entry premium, target, stop, time, evidence. Fires at a minute close when \|bias\| ≥ entry threshold, no signal is active on that index, it is within signal hours, and the feed is live. Open paper trades never block it. For gold and silver see **Bullion signal** (§1a). |
| **Signal status** | `active` (shown, can be paper-traded), `traded` (a paper trade was opened from it), `lapsed`, `reversed`. |
| **Signal TTL** | Time-to-live: how long a signal stays active untraded. Default 300 seconds. |
| **Stop (stop-loss)** | Price at which a trade is closed at a loss. Index options: entry × (1 − 15 %); expiry day: entry − \|delta\| × stop points. Bullion: 0.20 % of the future's price against the signal (above the entry for a short). |
| **Strength** | `round(|bias| × 100)`, shown 0–100 on the meter. |
| **Supertrend** | A trend-following indicator built from average true range (period 10, multiplier 3). Price above the line is bullish, below is bearish. |
| **Target** | Price at which a trade is closed at a profit. Index options: entry × (1 + 30 %); expiry day: entry + \|delta\| × target points. Bullion: 0.40 % of the future's price in the signal's favour (below the entry for a short). |
| **Tick rule** | Signing a trade that printed between bid and ask by the price move: up from the last trade, a buy; down, a sell; unchanged, the last trade's side. |
| **Trend (price trend)** | The indicator group reading direction and momentum of the index: EMA crossover, VWAP position, supertrend. |
| **VWAP (volume-weighted average price)** | Σ(price × volume) / Σ volume from session open, on the futures contract. Price above VWAP is bullish. |
| **Weight** | The share of the bias assigned to a group. Defaults: trend 0.40, OI 0.35, premium 0.25. On expiry day the OI weight is halved and redistributed. |

---

## 4. Paper trading and journal terms

| Term | Meaning |
|---|---|
| **Cost per trade** | The round-trip cost deducted from a paper trade, fixed at entry. Index options: a flat ₹60 per lot (brokerage, STT, exchange charges, GST). Bullion: ₹60 per lot plus 0.012 % of the round-trip value (CTT and charges scale with value). Configurable. |
| **Exit reason** | Why a paper trade closed: `TARGET`, `STOP`, `SQUARE_OFF`, `MANUAL`. |
| **Fill** | The price at which a paper trade is recorded as opened or closed. Entry fill is the LTP at the moment of the click (a live feed is required); exit fill is the LTP that triggered the exit. |
| **Fill quality** | How trustworthy an exit price is: `live` (feed healthy), `after_gap` (first tick after a feed outage triggered the exit, so the price may have jumped past target or stop), `stale` (square-off fired while the feed was down; the last price seen was used, with its age recorded). Anything other than `live` is badged in the journal. |
| **Gross P&L** | side × (exit − entry) × quantity, before costs; side is −1 for a short bullion future, else +1. |
| **Hit / hit rate** | A trade is a hit if net P&L > 0. Hit rate is hits ÷ trades. |
| **Journal** | The list of all paper trades with their outcomes, plus summary statistics. |
| **Net P&L** | Gross P&L minus cost per trade. The figure hit rate and summaries are based on. |
| **Open trade** | A paper trade not yet closed. Tracked tick by tick for target/stop. |
| **Paper trade** | A simulated trade opened by the trader clicking "Paper trade" on an active signal. Never placed with the broker. |
| **Quantity** | Lot size × lots (default 1 lot). For bullion, the point value × lots (GOLD 100, SILVER 30 per lot). |
| **Slippage** | Entry fill minus the signal's entry price: how far the price moved between the signal firing and the click. Recorded per trade. |
| **Square-off time** | When open paper trades are force-closed. Default 15:15 IST for index options, 23:00 (on the MCX clock) for bullion. |
| **Warning (bias reversed)** | A flag on an open paper trade whose direction opposes the current bias label (a CE or long-future trade while Bearish, a PE or short-future trade while Bullish). Set and cleared every minute as the label changes. Informational; does not close the trade. |

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
| **Feed health** | `connecting`, `connected`, or `disconnected`, plus last-tick timestamp, reconnect count, and subscribed instrument count. One socket carries both NSE and MCX keys; whether each is delivering is judged separately (index liveness, bullion status). |
| **Full mode** | The Upstox websocket subscription level that includes depth, OI, and Greeks, as opposed to LTP-only. |
| **Full quote** | Upstox's market-quote snapshot (`GET /v2/market-quote/quotes`): day OHLC, circuit limits, net change. Used once at start for bullion. Its `ohlc.close` is the live price, not yesterday's close. |
| **Historical candle API** | Upstox's candle endpoints: intraday (`/v3/historical-candle/intraday/...`, today's 1-minute candles, used for backfill) and by date range (`/v3/historical-candle/{key}/days/1/...`, daily candles, used for 52-week and contract ranges). History is per contract; there is no continuous futures series. |
| **Instrument key** | Upstox's unique identifier for one tradable instrument (for example `NSE_INDEX|Nifty 50`, `NSE_FO|12345`). Primary key for ticks and candles. |
| **Instrument master** | The daily file from Upstox listing every tradable instrument with symbol, expiry, strike, type, lot size, tick size. One file per exchange: `NSE.json.gz` for the indices, `MCX.json.gz` for bullion (cached as `data/mcx-instruments-YYYY-MM-DD.json.gz`). |
| **LTP (last traded price)** | The most recent trade price of an instrument. |
| **Market data provider** | The interface every feed implementation satisfies: connect, subscribe, unsubscribe, stream ticks, report health. Implementations: Upstox, replay, synthetic (tests). |
| **Market OHLC (`1d` row)** | In a full-mode tick, the open, high, low and close for the day. Sent for MCX futures; it is the bullion day range when present. |
| **OAuth** | The login flow in which the trader authorises TradeDisha in Upstox's web page and Upstox redirects back with a code that is exchanged for an access token. |
| **Protobuf** | Protocol Buffers, the binary encoding Upstox uses for websocket market data. |
| **Re-centre** | Moving the strike window when ATM has shifted by `recenter_strikes` (default 2): subscribe new strikes, unsubscribe old ones, fetch baselines for the new ones. |
| **Replay** | Feeding recorded ticks back through the system at real or accelerated speed. Used for tests, after-hours demos, load testing, and fault injection. |
| **Session** | (Auth sense) one day's login record. See also "trading day / session" in §1. |
| **Subscription** | Telling the websocket which instrument keys to stream. Subject to a provider-set cap on count. |
| **Synthetic candle** | A carry-forward candle created for a minute with no ticks (O=H=L=C=previous close, volume 0) so indicator windows stay aligned. |
| **Upstox** | The Indian broker whose free API is TradeDisha's market-data provider: OAuth login, REST (v2/v3) for instruments, quotes and candles, and the V3 websocket market feed. |
| **Websocket** | A persistent two-way connection. Used broker → backend (market data) and backend → browser (live updates). |

---

## 6. Architecture and software terms

| Term | Meaning |
|---|---|
| **Adapter** | A class that translates an external system's interface (Upstox) into TradeDisha's internal one (`MarketDataProvider`). |
| **asyncio** | Python's built-in framework for cooperative, single-threaded concurrency. The backend is an asyncio application. |
| **Batched insert** | Writing many rows in one database transaction (every 500 ms or 500 rows) instead of one at a time. |
| **Bullion desk** | `engine/bullion_desk.py:BullionDesk`: bullion bias, signals and paper trades together, on the MCX clock and bullion liveness. |
| **Bullion tracker** | `market/bullion.py:BullionTracker`: keeps the latest bullion ticks, the day range, the last bullion tick time and its own candle builder (900 minutes, since MCX runs to 23:30). Kept apart from the shared candle builder, which drives the bias engine, and from the tick store, so evening MCX ticks never stretch a replay. |
| **Candle builder** | The component that turns ticks into 1-minute candles and calls its close listeners on each minute boundary. The index builder drives the bias engine; bullion has its own (in the bullion tracker). |
| **Chain state** | The in-memory option chain for one index, with derived values (ATM, PCR, OI changes, max pain) kept up to date per tick. |
| **Coalescing** | When several updates arrive within one throttle window, sending only the latest state rather than every intermediate one. |
| **Config version** | One saved parameter set: a number (1, 2, 3, …), a tag typed by the trader and the values. The highest is in force; versions are never changed or removed. Each signal records the version it fired under. |
| **Degraded mode** | NSE market is live but auth is missing/expired or the index feed is silent (see Index liveness). Last-known data is shown greyed; bias still computed but greyed; no new signals; paper-trade entry and manual close refused; target/stop checked again from the first tick after the feed returns (`after_gap`); the square-off timer still fires at the last known price (`stale`). |
| **Display only** | Shown to the trader but never an input to the bias, signals or paper trades, and never recorded or replayed. Applied to bullion until E6; bullion now has its own pipeline (see Bullion desk). |
| **DTO (data transfer object)** | A typed structure that defines the shape of data crossing a boundary (API request/response, websocket frame). Pydantic models in `api/schemas.py` and the routers; mirrored by hand in `frontend/src/api/types.ts` (both sides change together). |
| **Evaluation offset** | `bullion.eval_offset_seconds`: how long after a minute close the bullion bias and signals run, so they never run at the same instant as the index engines. |
| **Event bus** | `events.py:EventBus`, the in-process publish/subscribe used for low-rate state changes only: feed health, auth, strike-window change, parameters changed. The per-tick and per-minute data (candles, bias, signals, trades) goes through callback lists on `FeedSession` instead. |
| **Event-loop lag** | How late asyncio runs a task compared to when it was due. Sampled every 100 ms; a sign the hot path is blocked. |
| **Fan-out** | Delivering each tick to several consumers (candle builder, chain state, paper manager, tick store) one after another from the tick bus. |
| **FastAPI** | The Python web framework used for REST and websocket endpoints. |
| **Fault injection** | Deliberately dropping or delaying replayed ticks to test reconnect and degraded-mode behaviour. |
| **Frame (websocket)** | One JSON message from backend to browser: `{type, ts, t_src, t_in, t_out, payload}`. |
| **`hello` frame** | The first websocket frame after connect, containing a full snapshot of current state so the client needs no event replay. |
| **Hop** | One leg of the data path used for latency measurement: exchange → ingest, ingest → sent, sent → received, received → painted. |
| **Hot path** | The code executed for every tick. Must never block; anything slow is moved off it. |
| **Hypothesis** | A Python property-based testing library; used to assert indicator scores stay within bounds for any input. |
| **Import-linter** | A tool that enforces which Python packages may import which. Named in the original plan; **not used**. The layering rule is kept by convention. |
| **Incremental computation** | Updating a running value (EMA, rolling sum, chain totals) from the latest input rather than recomputing over the whole window. |
| **Index liveness** | Whether the index feed is delivering: connected, and an NSE tick within `feed_live_max_tick_age_ms`. Bullion ticks on the same socket do not count, so gold ticking never hides an index outage. `FeedSession.feed_live()`. |
| **Ingest timestamp (`t_in`)** | When the backend received a tick. Start of the latency budget TradeDisha controls. |
| **Latency budget** | Agreed maximum time per hop at the 95th percentile, measured from arrival at the app (not from the exchange timestamp; the broker→app hop is shown separately). Total ingest → painted under 250 ms; minute close detected → signal painted under 100 ms. |
| **lightweight-charts** | TradingView's open-source canvas charting library, used for the candlestick chart. |
| **Market clock** | The single source of "what time is it and what is the market status?" for the whole backend. Reads the wall clock in live mode and the replayed tick timestamps in replay mode, so replays behave exactly as the live session did. No other code reads the system clock directly. There are two on one time source: the NSE clock and `mcx_clock` for MCX hours and holidays. |
| **Migration** | A versioned SQL script that changes the database schema; applied in order at startup. |
| **Minute close detected** | The moment the candle builder closes a 1-minute candle: the first tick of the next minute, or a 2-second wall-clock fallback when ticks are sparse. The 100 ms signal latency budget starts here; the detection delay itself is reported separately. |
| **mypy (strict)** | Python static type checker run with all strictness flags. |
| **orjson** | A fast JSON library. Named in the original plan; **not used** (frames are serialised with the standard library via pydantic). |
| **p50 / p95 / p99** | Percentiles: the value below which 50 %, 95 %, 99 % of samples fall. Latency targets are stated at p95. |
| **Parameter set** | The validated, typed form of the tunable values that shape a signal, as held in the config version in force. |
| **Pre-commit** | Git hook runner that executes ruff, ruff format, mypy, ESLint, Prettier and tsc over the whole project before each commit. Tests are not run by it (`make check` runs them). |
| **Prune (ticks)** | Deleting raw tick rows up to and including a date the trader chooses, from the Data panel, after a preview and confirmation. Candles, chain minutes, bias, signals, and paper trades are never pruned. Nothing is pruned automatically. |
| **Pure function** | A function whose output depends only on its inputs and which has no side effects. All indicator and signal maths is written this way so it is trivially testable. |
| **Pydantic** | Python library for typed, validated data models; used for settings, the parameter set, DTOs, and boundary objects. |
| **Repository (data access)** | A thin module that owns the SQL for one table or aggregate. |
| **REST** | The HTTP request/response API (`/api/...`) used for snapshots, history, and all mutations. |
| **Revert (config)** | Putting an old config version's values back in force by saving them as a new version. |
| **ruff** | Python linter and formatter. |
| **SQLAlchemy Core** | An SQL-expression library. Named in the original plan; **not used**: the backend talks to SQLite with the standard `sqlite3` module. |
| **SQLite (WAL mode)** | The embedded database file holding all persisted data. Write-Ahead Logging mode lets reads proceed while the writer task commits. |
| **Standby mode** | NSE closed or holiday: no index ticks expected, last-known state shown under an amber "NSE market closed" (or holiday) banner, and a quiet index feed is not an outage. On the live feed the socket stays connected for MCX bullion until it closes. |
| **Static settings** | Values that need a restart and are not about the algorithm (credentials, paths, indices, market hours). From `.env`. Distinct from the parameter set. |
| **Store (frontend)** | A client-side state container (Zustand) holding live data per index; updated from websocket frames and rendered once per animation frame. |
| **TanStack Query / Virtual** | React libraries for server-state caching and for rendering only visible table rows. Named in the original plan; **not used** (plain `fetch` in `api/client.ts`; the 21-row chain needs no virtualisation). |
| **Throttle (leading-edge)** | The minimum gap between pushes on one websocket channel per index (50 ms for ticks, 500 ms for chain). The first update after a quiet gap goes out immediately; later ones wait for the gap, and only the latest state is sent. |
| **Tick bus** | `feed/bus.py:TickBus`: a synchronous fan-out that hands each tick to every subscriber in turn (session, chain, flow, outcomes, paper trades, bullion tracker and desk). Subscribers must not block. |
| **Tick store** | The component that batches ticks into SQLite: index ticks into `ticks`, bullion ticks into `bullion_ticks`. Flushed twice a second; not used in replay. |
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
| `candles_1m` | one 1-minute candle for one instrument, with its buyer- and seller-initiated volume where known |
| `chain_minutes` | one strike of one index at one minute close (CE and PE values) |
| `bias_minutes` | one index's bias and evidence at one minute close |
| `signals` | one signal (index or bullion) with its evidence, final status and the config version it fired under |
| `signal_outcomes` | what one index signal's option did next: result, best/worst price, spot moves |
| `config_versions` | one saved set of tunable parameters, numbered and tagged |
| `paper_trades` | one paper trade from open to close, including exit fill quality |
| `app_state` | one key/value of application state (the schema version itself is SQLite's `PRAGMA user_version`) |
| `bullion_ticks` | one bullion (MCX) tick: the `ticks` columns plus the feed's day open, high and low |
| `feed_events` | one operational event (session start, disconnect, gap, bullion gap, re-centre, backfill, ticks pruned) |
| `latency_samples` | one hop's latency percentiles for one minute |

---

## 8. Abbreviations

| Abbrev. | Expansion |
|---|---|
| ATM | at the money |
| ATP | average traded price |
| ATR | average true range (used inside supertrend) |
| CE / PE | call European / put European (NSE option suffixes) |
| CTT | Commodity Transaction Tax |
| DII | Domestic Institutional Investors |
| EMA | exponential moving average |
| F&O | futures and options |
| FII | Foreign Institutional Investors |
| GST | Goods and Services Tax (on brokerage) |
| IST | Indian Standard Time |
| ITM / OTM | in / out of the money |
| IV | implied volatility |
| LTP | last traded price |
| MCX | Multi Commodity Exchange of India |
| NSE / BSE | National / Bombay Stock Exchange |
| OHLCV | open, high, low, close, volume |
| OI | open interest |
| P&L | profit and loss |
| PCR | put-call ratio |
| ROC | rate of change |
| STT | Securities Transaction Tax |
| TBQ / TSQ | total buy / sell quantity |
| TTL | time to live |
| VWAP | volume-weighted average price |
| WS | websocket |
