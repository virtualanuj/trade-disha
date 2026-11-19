# How the signal engine works

This document explains, end to end, how TradeDisha decides to raise a "buy call" or "buy
put" signal: what data goes in, how it becomes a single bias number each minute, the two
entry rules, how targets and stops are set, how a signal ends, and how every signal is
scored afterwards. Section 13 explains the separate engine for gold and silver, which
buys or sells a future instead of an option.

It describes the code as it stands. The design reference is `docs/spec.md` §8 (indicators)
and §9 (signal engine); every tunable number mentioned here is a config parameter
(section 11) and the values quoted are the shipped defaults.

Each section starts with a **Note** that explains the terms it is about to use.

## Contents

1. [The big picture](#1-the-big-picture)
2. [Inputs](#2-inputs)
3. [Step 1: nine indicators vote](#3-step-1-nine-indicators-vote)
4. [Step 2: the votes become one bias](#4-step-2-the-votes-become-one-bias)
5. [Step 3: order flow](#5-step-3-order-flow)
6. [Step 4: the entry rules](#6-step-4-the-entry-rules)
7. [Step 5: building the signal](#7-step-5-building-the-signal)
8. [Step 6: how a signal ends](#8-step-6-how-a-signal-ends)
9. [The shadow engine](#9-the-shadow-engine)
10. [Scoring every signal](#10-scoring-every-signal)
11. [Parameters](#11-parameters)
12. [Where the code is](#12-where-the-code-is)
13. [Bullion signals: gold and silver](#13-bullion-signals-gold-and-silver)

---

## 1. The big picture

> **Note: terms used in this section**
>
> - **Index**: a basket of stocks quoted as one number. TradeDisha follows two, NIFTY and
>   BANK NIFTY. An index cannot be bought directly.
> - **Spot**: the current value of the index itself.
> - **Option**: a contract whose price depends on the index. A **call** (written **CE**)
>   gains when the index rises; a **put** (written **PE**) gains when it falls.
> - **Premium**: the price of an option, in rupees.
> - **Signal**: a suggestion to buy one specific option now, with an entry price, a target
>   price and a stop price. `BUY_CE` means buy the call, `BUY_PE` means buy the put.
> - **Bias**: one number from −1 to +1 that sums up the evidence. +1 is fully bullish
>   (expecting a rise), −1 fully bearish (expecting a fall), 0 no view.
> - **Tick**: one update from the broker's feed for one instrument (latest price, and
>   sometimes quantity, open interest and quote data).
> - **Minute close**: the moment a 1-minute interval ends and its price bar is final.
> - **Paper trade**: a simulated trade tracked by the app. No real order is ever sent.

The engine is a pipeline. Ticks come in continuously; most of the thinking happens once
per minute, per index.

```
ticks ─┬─> 1-minute candles ─┐
       ├─> option chain ─────┼─> 9 indicators ─> bias (−1..+1) ─┐
       │                     │      (every minute close)        │
       └─> order flow (about once a second) ────────────────────┼─> entry rule ─> signal
                                                                │
                                           live feed, signal hours, no active signal
```

In one sentence: **nine indicators each vote between −1 and +1, the votes are averaged
into a bias, and when the bias is strong enough (and a few safety checks pass) the engine
raises a signal to buy the call or the put nearest the current index level.** Sections 1
to 12 describe this index engine; gold and silver run a smaller engine of their own that
buys or sells a future (section 13).

Three properties hold throughout:

- **Each index is independent.** NIFTY and BANK NIFTY have their own bias, their own
  active signal and their own state.
- **At most one active signal per index.** A new one cannot fire until the current one
  has ended.
- **The engine only suggests.** A signal never opens a trade by itself. You choose
  whether to paper-trade it.

---

## 2. Inputs

> **Note: terms used in this section**
>
> - **Candle** (or **bar**): the open, high, low and close price of one minute.
> - **Future**: a contract to buy the index at a later date. It trades like a share, so
>   unlike the index it has real traded volume and a real order book.
> - **Strike**: the index level an option is written against. NIFTY strikes are 50 points
>   apart, BANK NIFTY 100; that gap is the **strike step**.
> - **Option chain**: the table of all calls and puts across strikes for one expiry date.
> - **Leg**: one side of a strike in the chain, either its call or its put.
> - **ATM (at the money)**: the strike nearest to the current spot.
> - **Expiry**: the date an option contract ends. **Expiry day** is that date; option
>   prices behave very differently on it, so several rules change.
> - **LTP**: last traded price.
> - **Open interest (OI)**: the number of option contracts currently open (held and not
>   yet closed). Rising OI means new positions are being created.
> - **IV (implied volatility)**: how large a move the option's price is assuming, as an
>   annual percentage. Higher IV means more expensive options.
> - **Bid / ask**: the best price buyers are offering (bid) and the best price sellers are
>   asking (ask). A buyer who wants to trade immediately pays the ask.

Per index, the engine reads:

| Input | Built from | Used for |
|---|---|---|
| Spot candles | spot ticks, 1-minute bars | EMA cross, supertrend |
| Futures candles and VWAP | futures ticks | position against VWAP |
| Option chain | option ticks for 10 strikes either side of ATM | OI and premium indicators, the option a signal names |
| Chain history | one snapshot per minute, last 60 kept | anything that compares "now" with "N minutes ago" |
| Order flow | quote and volume fields on futures and ATM option ticks | the trigger entry rule |

The net-volume histogram under the chart (buy minus sell volume per minute, signed from
the same futures ticks) is shown for the trader only; no indicator or rule reads it.

**Which strike is "ATM" here.** The chain is centred on a strike, and that centre only
moves when spot has travelled 2 strikes away from it (`chain.recenter_strikes`). So the
strike the engine calls ATM can be up to about two strikes from the true nearest strike.
Indicators and signals both use this centre strike.

**Time.** A minute is identified by the timestamp of its start (`minute_ts`). The engine
evaluates it at the close, `minute_ts + 60 s`. All time comes from the market clock, which
in replay is driven by the recorded tick timestamps, so a replayed day behaves as it did
live.

---

## 3. Step 1: nine indicators vote

> **Note: how to read a vote**
>
> Every indicator returns a **score** from −1 (bearish) to +1 (bullish), a short text
> note, and a **quality**:
>
> - `ok`: the score counts.
> - `warming`: there is not enough history yet (for example a 21-minute average needs 21
>   minutes). The score is 0 and the indicator is **left out** of the average, not
>   counted as neutral.
>
> **Clamp** means "limit to a range": a value above +1 becomes +1 and below −1 becomes −1.
> "Full strength" is the reading at which an indicator's score reaches ±1.

The indicators are in three groups of three, and since Milestone E12 a fourth, smaller
macro group (section 3.4) reads the dollar, crude and gold. They are pure functions in
`backend/tradedisha/indicators/`.

### 3.1 Trend group: what is the price doing

> **Note: terms used here**
>
> - **EMA (exponential moving average)**: an average of recent closing prices that gives
>   more weight to the newest ones. A "fast" EMA (9 minutes) reacts quickly, a "slow" one
>   (21 minutes) lags. Fast above slow suggests an uptrend.
> - **VWAP (volume-weighted average price)**: the average price paid today, weighted by
>   how much traded at each price. Price above VWAP means buyers today are, on average,
>   in profit; it is widely used as the day's fair-value line.
> - **ATR (average true range)**: the typical size of a one-minute price swing recently.
> - **Supertrend**: a line that trails the price at a distance of a few ATRs. When price
>   closes through the line, the line jumps to the other side: a **flip**. Price above the
>   line is read as an uptrend.
> - **tanh**: a smooth S-shaped curve that turns any number into one between −1 and +1.

| Indicator | What it measures | Score |
|---|---|---|
| `ema_cross` | Gap between EMA 9 and EMA 21 of spot closes, as % of the slow EMA | `tanh(8 × gap%)`. A gap of +0.10 % scores about +0.66. Needs 21 bars. |
| `vwap_position` | Futures close against futures VWAP, in % | `clamp(distance% / 0.3)`. 0.3 % above VWAP is full strength. |
| `supertrend` | Side of the supertrend line (period 10, multiplier 3) the spot is on | +1 above, −1 below, scaled by `bars since flip / 3` so a fresh flip counts 1/3, then 2/3, then fully. Needs 11 bars. |

### 3.2 OI group: what positions are being built

> **Note: terms used here**
>
> - **PCR (put-call ratio)**: total put OI divided by total call OI. Above 1 means more
>   puts are open than calls. The engine reads a high PCR as **bullish**, on the usual
>   view that puts are mostly sold by large players who expect the market to hold up.
> - **Build-up**: a reading of what happened in an option over the last minute, from the
>   direction of its price and its OI together:
>
>   | Price | OI | Name | Meaning |
>   |---|---|---|---|
>   | up | up | long build-up | new buyers are coming in |
>   | up | down | short covering | sellers are buying back to exit |
>   | down | up | short build-up | new sellers (writers) are coming in |
>   | down | down | long unwinding | buyers are exiting |
>
> - **Writer**: someone who sells an option they do not hold, collecting the premium.
> - **Max pain**: the strike at which, if the index expired there, option buyers in total
>   would be paid the least. The index is often said to drift towards it near expiry.

| Indicator | What it measures | Score |
|---|---|---|
| `pcr` | PCR over ATM ± 5 strikes | `clamp((PCR − 1.0) / 0.5)`. PCR 1.5 is fully bullish, 0.5 fully bearish. |
| `oi_change_atm` | Build-up in each call and put within ATM ± 2 strikes over the last minute | See below. |
| `max_pain_drift` | How far max pain has moved in 15 minutes, in strike steps | `clamp(steps / 2)`. Up 2 strikes is fully bullish. Needs 16 minutes of chain history. |

**The build-up vote in detail.** For every leg in range that has a build-up reading, the
direction of its **premium** decides the side and the size of its **OI change** is the
weight:

| Leg | Premium rose (long build-up, short covering) | Premium fell (short build-up, long unwinding) |
|---|---|---|
| Call | bullish | bearish |
| Put | bearish | bullish |

The score is `(bullish OI − bearish OI) / (bullish OI + bearish OI)`. A leg whose price or
OI did not change in the minute is ignored.

### 3.3 Premium group: are option prices agreeing

> **Note: terms used here**
>
> - **Rate of change (ROC)**: the percentage change of a price over a period.
> - **Divergence**: two things that normally move together moving apart, for example the
>   index rising while call premiums fail to rise. It is treated as a warning.

All three compare the ATM call and put now with N minutes ago, using the chain history.

| Indicator | What it measures | Score |
|---|---|---|
| `premium_momentum` | 5-minute ROC of the ATM call minus that of the ATM put | `clamp(spread / 20)`. Calls outpacing puts by 20 percentage points is fully bullish. |
| `iv_change` | Change in ATM IV over 15 minutes, with the direction of the spot move | Only **rising** IV counts: `sign(spot move) × clamp(IV change / 2, 0, 1)`. IV up 2 points while spot rises is +1; while spot falls, −1. Falling IV scores 0. |
| `premium_confirmation` | Whether premiums back the 5-minute spot move | Spot up and calls up (by at least as much as puts fell): `+clamp(call ROC / 10)`. Spot down and puts up: `−clamp(put ROC / 10)`. If they disagree: −0.5 on an up-move, +0.5 on a down-move, so a divergence pulls **against** the move. Spot flat: 0. |

### 3.4 Macro group: the dollar, crude and gold (Milestone E12)

> **Note: terms used here**
>
> - **Dollar index (DXY)**: the US dollar against six major currencies. Upstox does not
>   carry it, so TradeDisha rebuilds it (below).
> - **Risk-off**: money leaving shares for safety, such as gold.
> - **`info`**: a reading shown with the evidence but never given weight.

Each reading is one instrument's move over the last 30 minutes of its 1-minute closes
(`macro.window_minutes`), scored `sign × clamp(move% / full%)`. Rising dollar, a weaker
rupee, rising crude and rising gold are all **bearish** for NIFTY and BANK NIFTY.

| Indicator | Instrument | Score (index) |
|---|---|---|
| `dollar_index` | dollar-index proxy from NSE's USD/INR, EUR/INR, GBP/INR, JPY/INR futures | `−clamp(move / 0.15)`: a strong dollar draws foreign money out |
| `usd_inr` | USD/INR near-month future | `−clamp(move / 0.10)`: a weaker rupee |
| `crude` | MCX CRUDEOIL near-month future | `−clamp(move / 0.80)`: a bigger import bill and inflation |
| `gold` | MCX GOLD near-month future | `−clamp(move / 0.40)`: money seeking safety |
| `silver` | MCX SILVER near-month future | shown as `info`, never scored: half industrial, its sign is unclear |
| `gift_nifty` | GIFT Nifty's overnight move, NIFTY only (Milestone E14) | `+clamp(move / 0.50)` (follow) or `−` (fade), fading to nothing over the first 30 minutes |

**The dollar-index proxy.** From the four rupee rates: euro-dollar = EUR/INR ÷ USD/INR,
pound-dollar = GBP/INR ÷ USD/INR, dollar-yen = USD/INR ÷ (JPY/INR ÷ 100). The proxy is
`euro-dollar^−0.693 × dollar-yen^0.164 × pound-dollar^−0.143`, the real DXY's weights for
those three currencies (83 % of it) scaled to sum to 1. Only its % move is used.

A reading is `warming` (no weight) when there is no price yet, fewer than 31 closes, or
its last tick is more than 3 minutes old (`macro.max_age_seconds`), for example the
currency market after 17:00. Without the live feed (synthetic, or replay without
`replay_bullion`) there is no macro data at all.

**Worked example:** crude up 0.40 % in 30 minutes scores −0.40 / 0.80 = **−0.50**.

**GIFT Nifty gap (NIFTY only).** GIFT Nifty trades on NSE IX while NSE is shut. Upstox
refreshes it every 2 minutes, so during market hours it adds nothing to the NIFTY future
the bias already reads. What it does add is the overnight move: GIFT's last price before
09:15 against its own price at the previous NSE close (15:29), so its usual premium over
spot cancels out. The vote is that move against `macro.gift_full_pct` (0.50 %), signed by
`macro.gift_direction` (`follow`: a gap up is bullish; `fade`: a gap up is bearish), and
shrinks in a straight line to nothing over `macro.gift_fade_minutes` (30) after the open;
after that it is shown as `info`. With no reading (Upstox had no price, or synthetic) it is
`warming`. Example: on 19/11/2026 GIFT went from 25 237.5 to 25 154.0, −0.33 %; at the
09:19 close (5 minutes in) it scores −0.33 / 0.50 × (1 − 5/30) = **−0.55**.

---

## 4. Step 2: the votes become one bias

> **Note: terms used in this section**
>
> - **Weight**: the share of the final answer a group carries.
> - **Neutral band**: the range around zero in which the bias is treated as "no view".
> - **Strength**: the bias without its sign, as a whole number from 0 to 100.

At every minute close of the spot candle, `BiasEngine` runs all nine indicators and
`aggregate()` combines them.

**1. Average within each group.** A group's score is the plain average of its `ok`
indicators. Warming indicators are left out, so with two of three ready the group is the
average of those two. If none are ready the group scores 0.

**2. Weight the groups.**

| Group | Normal weight | Expiry-day weight | No live macro price |
|---|---|---|---|
| Trend | 0.36 | 0.443 | 0.40 |
| OI | 0.315 | 0.158 | 0.35 |
| Premium | 0.225 | 0.277 | 0.25 |
| Macro | 0.10 | 0.123 | 0 |

Macro takes its share first (`weights.macro`, 0.10) and trend, OI and premium keep their
proportions 0.40 / 0.35 / 0.25 in the rest. On expiry day OI is distorted by positions
being closed, so its weight is halved (`expiry_oi_weight_factor = 0.5`) and the share it
gives up is handed to the other groups in proportion to their own weights. When **no
macro reading is `ok`**, the macro share is handed back the same way, so the bias is
exactly what it was before E12 (last column).

**Switching a factor off.** Every factor is on by default. In **Config → Factors** each
index and metal lists its factors with a switch; a flip is saved at once as a new config
version tagged, for example, `Factor NIFTY.pcr: off`, and applies from the next minute
close. A factor switched off is still worked out and shown in the Evidence panel (its
switch there shows the state, read only; the row is dimmed and marked "(off)") but carries
no weight: it is left out of its group's average, so the group's other ready factors share
the group's weight. If every factor of a group is off, the group's share is handed to the
other groups in proportion, as with no live macro price. Switches are per index or metal
(crude off on NIFTY leaves BANK NIFTY alone). Until the next minute close the Evidence row
says "off from the next minute close".

**3. Sum and clamp.** `bias = Σ (group weight × group score)`, clamped to −1..+1.

**4. Label.** With a neutral band of 0.20: bias ≥ +0.20 is **Bullish**, ≤ −0.20 is
**Bearish**, otherwise **Neutral**. Strength is `round(|bias| × 100)`.

**Worked example** (a normal day, all indicators ready, no live macro price, so the
weights are the last column above):

| Group | Indicator scores | Group score | × weight | Contribution |
|---|---|---|---|---|
| Trend | 0.66, 0.80, 1.00 | 0.82 | 0.40 | 0.328 |
| OI | 0.40, 0.20, 0.00 | 0.20 | 0.35 | 0.070 |
| Premium | 0.60, 0.00, 0.50 | 0.37 | 0.25 | 0.092 |
| | | | **Bias** | **0.49** |

That is Bullish with strength 49: just short of the 0.50 needed to fire under the default
rule.

Every minute's bias is stored in `bias_minutes` together with its **full breakdown**:
each indicator's score, note, weight and contribution. The same breakdown is copied onto
any signal fired from it, so you can always see why.

---

## 5. Step 3: order flow

> **Note: terms used in this section**
>
> - **Order book**: the list of buy orders (bids) and sell orders (asks) waiting at each
>   price. The feed gives the quantity over the best five price levels on each side.
> - **Book imbalance**: how lopsided the book is, `(buy qty − sell qty) / (buy qty + sell qty)`.
>   +1 means only buyers are waiting, −1 only sellers.
> - **Total buy / sell quantity**: all buy and all sell orders pending at the exchange for
>   that instrument, not only the best five levels.
> - **Signed trade**: a trade labelled by who was impatient. A trade at the ask means a
>   buyer paid up (counted +); at the bid means a seller hit the bid (counted −).
> - **Order-flow score**: the engine's summary of all this, from −1 (selling pressure) to
>   +1 (buying pressure).

The bias looks at minutes. Order flow looks at **seconds**: who is leaning on the market
right now. It is computed by `FlowTracker` (`market/flow.py`) from every tick of the
index's future and its chain options, and re-read about once a second per index.

It has three parts, each from −1 to +1, each smoothed over the last 15 seconds
(`flow.window_seconds`):

| Part | Weight | How it is measured |
|---|---|---|
| Futures book | 0.4 | Average book imbalance of the future. Each reading is the mean of the five-level imbalance and the total buy/sell quantity imbalance, whichever are available. |
| Futures trades | 0.3 | Net signed volume ÷ total volume traded in the window. A trade between bid and ask counts in the total but on neither side. Each trade is judged against the quote as it stood **before** that tick. |
| Options | 0.3 | (ATM call flow − ATM put flow) ÷ 2, where a leg's flow is the mean of its own book and trade readings. Needs both legs. |

The score is the weighted average of the parts **that have data**. A part with nothing in
the window is unknown and dropped, with the remaining weights scaled up; it is never
counted as zero. If no part has data the score is "unknown".

The score is shown under the evidence table. It does **not** feed the bias. It is used
only by the trigger entry rule below.

---

## 6. Step 4: the entry rules

> **Note: terms used in this section**
>
> - **Entry rule**: the condition under which a signal fires.
> - **Gate**: a check that must pass before firing. When a signal does not fire, the
>   engine records which gate stopped it, and the signal card shows that reason.
> - **Setup**: in the trigger rule, a direction the bias favours that is waiting for order
>   flow to confirm it. A setup is not yet a signal.
> - **Spread**: the gap between bid and ask. Here it is expressed as a percentage of the
>   **mid price** (halfway between them). A wide spread makes a trade expensive to enter.
> - **Feed live**: the broker connection is up and the last tick is no more than 5 seconds
>   old.
> - **Signal hours**: the part of the day in which signals may fire.

There are two entry rules. `signal.entry_mode` chooses which one is **live**; the other
runs in shadow (section 9). The default live rule is `minute_close`.

### 6.1 What happens at every minute close (both rules)

`SignalEngine.on_bias()` runs for the index, in this order:

1. **Lapse** any active signal whose time has run out (section 8).
2. **Reversal check**: if there is an active signal and the new bias no longer supports
   it, end it as `reversed` (section 8).
3. **Re-arm bookkeeping** (only if `bias.rearm_hysteresis` > 0; off by default).
4. Hand over to the entry rule.

### 6.2 Rule A, `minute_close` (the default)

The signal fires **at the minute close**, at the option's last traded price, if every
gate passes. Gates are checked in this order and the first failure is the reason shown:

| # | Gate | Reason code if it fails |
|---|---|---|
| 1 | \|bias\| ≥ `entry_threshold` (0.50) | `below_threshold` |
| 2 | No signal is active on this index | `active_exists` |
| 3 | Not blocked by re-arm (off by default) | `rearm` |
| 4 | Within signal hours | `outside_hours` |
| 5 | Feed is live | `feed_down` |
| 6 | The ATM option has a price | `no_price` |

Direction is the sign of the bias: positive fires `BUY_CE`, negative fires `BUY_PE`.

### 6.3 Rule B, `trigger`

This rule splits the decision in two, to enter earlier in a move and only when buyers or
sellers are visibly acting.

**At the minute close: set up or drop.**

- If \|bias\| ≥ `setup_threshold` (0.35, deliberately lower than 0.50), the engine
  remembers that bias as the **setup** for the index. The gate reads `flow_not_confirmed`
  (or `active_exists` if a signal is already active).
- If \|bias\| is below it, any setup is dropped and the gate reads `no_setup`.
- If the setup's direction flipped from the previous minute, the "how long has flow
  agreed" timer restarts.

**About once a second: wait for the flow.** `on_flow()` receives the order-flow score and
fires only when all of this is true:

| # | Condition | Reason code if not |
|---|---|---|
| 1 | There is a setup, and no active signal | (the minute-close reason stays) |
| 2 | The flow score, in the setup's direction, is ≥ `flow.trigger_score` (0.25). For a bearish setup that means a score ≤ −0.25. An unknown score fails. | `flow_not_confirmed` |
| 3 | It has stayed there continuously for `flow.hold_seconds` (5 s). Any dip resets the timer. | `flow_not_confirmed` |
| 4 | Re-arm, signal hours and live feed, as in rule A | `rearm`, `outside_hours`, `feed_down` |
| 5 | The option has both a bid and an ask, and the spread is ≤ `signal.max_spread_pct` (1 % of mid) | `spread_wide` (or `no_price` if the strike is missing) |

The signal then fires **inside the minute**, priced at the **ask** (what a buyer would
actually pay), and records the flow score that triggered it.

### 6.4 Signal hours

Signals may fire from market open (09:15 IST) until `signal.last_signal_time` (15:00), or
until `signal.last_signal_time_expiry` (13:00) on expiry day, and only on trading days.
The cut-off is earlier on expiry day because option prices decay and swing fastest in the
final hours.

Hours are enforced for the live and replay feeds. The synthetic feed runs around the
clock and ignores them unless `TRADEDISHA_ENFORCE_SIGNAL_HOURS=true`.

### 6.5 Re-arm (optional, off by default)

> **Note:** **hysteresis** means requiring a signal to back off by a margin before it may
> trigger again, to stop it flickering on and off around a threshold.

With `bias.rearm_hysteresis` = h > 0, after a signal ends the same direction cannot fire
again until \|bias\| has dipped below `threshold − h` at some minute close. With the
default of 0 there is no such block: if a signal lapses and the bias is still strong, a
new one fires at the next minute close.

### 6.6 What does not gate a signal

Open paper trades never block a new signal. The only link is a warning: if the bias turns
against an open paper trade's direction, the trade is flagged `bias_reversed` until the
bias stops opposing it. Nothing is closed automatically for that reason.

---

## 7. Step 5: building the signal

> **Note: terms used in this section**
>
> - **Entry price**: the option price the signal assumes you buy at.
> - **Target**: the price at which to take profit. **Stop**: the price at which to accept
>   the loss and exit.
> - **Lot size**: options trade in fixed bundles; one lot is that many units.
> - **Delta**: how much an option's price moves for a 1-point move in the index. An ATM
>   option has a delta near 0.5, so a 40-point index move changes it by about 20 rupees.
>   A put's delta is negative; the engine uses its size.
> - **Black-Scholes**: the standard formula for an option's theoretical price and delta.
> - **Risk-free rate**: the interest rate assumed in that formula (6.5 % a year here).
> - **TTL (time to live)**: how long a signal stays valid before it expires unused.

**Which option.** Always the chain's ATM strike for the nearest expiry: its call for
`BUY_CE`, its put for `BUY_PE`.

**Entry price.** The option's LTP under `minute_close`; its ask under `trigger`.

**Target and stop on a normal day** are percentages of the entry price:

- target = entry × 1.30 (`target_pct = 30`)
- stop = entry × 0.85 (`stop_pct = −15`), never below ₹0.05

So an entry at ₹100 gives target ₹130 and stop ₹85: risking 15 to make 30.

**Target and stop on expiry day** are set in **index points** instead, because on expiry
day premiums are small and a fixed percentage would be hit by noise:

| Index | Target move | Stop move |
|---|---|---|
| NIFTY | 40 points | 20 points |
| BANK NIFTY | 100 points | 50 points |

The index move is converted to an option price move with delta:

- target = entry + \|delta\| × target points
- stop = entry − \|delta\| × stop points, never below ₹0.05

Delta comes from the feed. If the feed has none, it is computed with Black-Scholes from
spot, strike, time to the 15:30 close on expiry day, the option's IV (15 % if unknown) and
the risk-free rate. Example: NIFTY call at ₹60 with delta 0.5 gives target 60 + 0.5 × 40 =
₹80 and stop 60 − 0.5 × 20 = ₹50.

**What a signal records** (table `signals`):

| Field | Meaning |
|---|---|
| `direction`, `trading_symbol`, `strike`, `expiry`, `lot_size` | what to buy |
| `entry_price`, `target_price`, `stop_price` | the three prices |
| `target_basis` | `pct` or `points`; with points, `target_points`, `stop_points` and `delta_used` |
| `bias`, `strength`, `breakdown_json` | the bias that produced it, with every indicator's vote |
| `minute_ts`, `ts_fired` | the minute evaluated and the moment it fired |
| `expires_at` | `ts_fired` + TTL (300 s) |
| `entry_ask`, `spread_pct` | the ask and spread at firing, whichever rule fired |
| `entry_mode`, `shadow`, `flow_score` | which rule fired it, whether it was the shadow rule, and the flow score for a trigger signal |
| `config_version` | the config version in force when it fired (section 11) |
| `status`, `status_ts` | where it is in its life (next section) |

**Live levels while the signal waits.** The three prices above are the **fired** levels
and are never changed. While the signal is active, the card also shows **live** levels:
the same rule applied to the option's price now. A percentage signal keeps the
target/entry and stop/entry ratios it fired with (so editing the config later does not move
it); an expiry-day signal re-applies its index points through the option's **current**
delta. They are sent once a second. When you paper-trade the signal, the trade opens at
the price then and takes the live target and stop at that price (`rescale_levels` in
`engine/signals.py`).

---

## 8. Step 6: how a signal ends

A signal starts `active` and ends in exactly one of three ways:

```
                 ┌─> traded     you opened a paper trade on it
   active ───────┼─> lapsed     5 minutes passed and nobody traded it
                 └─> reversed   the bias stopped supporting it
```

| Ending | When | Checked |
|---|---|---|
| `traded` | You open a paper trade from the signal. | On your action. |
| `lapsed` | `signal_ttl_seconds` (300 s) pass since it fired. | Twice a second. |
| `reversed` | At a minute close the bias has the opposite sign, **or** has fallen inside the neutral band (\|bias\| < 0.20). | Every minute close. |

Notes on `reversed`: the bias only needs to drop below 0.20, not all the way through zero.
A bias that weakens from 0.55 to 0.30 does **not** reverse the signal; it stays active
until it lapses.

Once a signal ends, the index is free and the next qualifying evaluation can fire a new
one. Ending a signal has no effect on a paper trade already opened from it: the trade
runs on its own target, stop and the 15:15 square-off.

**Degraded feed.** If **index (NSE)** ticks stop for more than 5 seconds during NSE market
hours, the feed is not live (gold and silver ticks on the same connection do not count,
and silence after the close is not an outage): no signal fires (`feed_down`), paper-trade entry and manual close are refused,
and the first fill after the gap is marked as such. Signals resume by themselves when
ticks return.

---

## 9. The shadow engine

> **Note:** a **shadow** run executes a rule for real on live data but keeps its results
> separate, so it can be measured without anyone acting on it.

Two `SignalEngine` objects run side by side on the same bias and the same order flow:

- the **live** engine runs the rule named in `signal.entry_mode`;
- the **shadow** engine runs the other one.

Each has its own active signal, setup and gates, so they do not interfere. Shadow signals
are stored with `shadow = true`, appear greyed and tagged in "Signals today", are scored
on their own scorecard line, and **cannot be paper-traded** (the attempt is refused).

The purpose is a fair comparison: both rules see the same days, so the scorecard shows
which would have done better before you switch `entry_mode`. Switching is a parameter
change and takes effect at the next minute close.

---

## 10. Scoring every signal

> **Note: terms used in this section**
>
> - **Outcome**: the record of what a signal's option did after it fired.
> - **Horizon**: how long the option is followed (30 minutes by default).
> - **Square-off**: the time all intraday positions are closed (15:15).
> - **Late share**: how much of the favourable index move had already happened before the
>   signal fired. 0 means it fired at the very start of the move, 1 at the very end.

Every index signal, live or shadow, traded or not, and however it ended, is followed by
`OutcomeTracker` (`engine/outcomes.py`) from the moment it fires until the earlier of the
horizon (`outcome_horizon_minutes = 30`) and the square-off time.

**Result.** Whichever of the signal's own target or stop the option's LTP touches first:

| Result | Meaning |
|---|---|
| `target` | reached the target first |
| `stop` | reached the stop first |
| `neither` | the horizon ended with neither touched |
| `open` | still being followed |

Also recorded: the best and worst option price over the whole horizon (followed even
after the result is decided, so "stopped out just before a run to target" is visible),
the option price 1, 5 and 15 minutes after firing, and the index move.

Bullion signals are not scored this way: the yardstick measures NSE spot moves (section
13).

**Late share** = `pre-move / (pre-move + best move after)`, where pre-move is how far spot
had already gone in the signal's direction over the 10 minutes before firing, and best
move is the furthest it went in that direction afterwards. Moves against the signal count
as 0.

**The scorecard** groups signals by entry rule and by live or shadow, with one line for
all indices and one per index. Per line: number of signals, how many are scored, the
percentage that hit target, stop or neither, the average best and worst move as % of
entry, and the average late share.

Where to see it:

- in the app, the Outcome column and count line in "Signals today";
- `GET /api/signals/scorecard`;
- offline, over recorded days: `cd backend && uv run python -m tradedisha.tools.score --db ../data/live.sqlite [--params trial.toml]`.
  This replays the days in a scratch copy, so trying different parameters never touches
  the recording.

---

## 11. Parameters

> **Note:** a **config version** is one saved set of all the parameters, with a number
> and a tag you type. The highest version is the one in force.

Everything below is edited in the app (the **Config** button in the top bar) and
validated by `parameters/model.py`. Each save is a new numbered version that applies from
the next minute close; an invalid save is rejected and the previous values stay in force.
Any earlier version can be reverted to. Versions are stored in the `config_versions`
table; `config/params.toml` only supplies version 1 for a new database.

The factor switches (section 4) are parameters too, but are not typed in the editor: each
flip in the Factors tab is its own version with a fixed tag such as `Factor NIFTY.pcr:
off`.

Each signal records the version in force when it fired (`config_version`). It appears as
a small `v7` on the signal card and in "Signals today"; hovering it shows that version's
values and highlights the ones that differ from the current config.

| Parameter | Default | Effect |
|---|---|---|
| `weights.trend` / `oi` / `premium` | 0.40 / 0.35 / 0.25 | group shares of the bias; must sum to 1 |
| `weights.expiry_oi_weight_factor` | 0.5 | OI weight multiplier on expiry day |
| `weights.macro` | 0.10 | the macro group's share; the three above keep their proportions in the rest; handed back while no macro price is live |
| `macro.window_minutes` | 30 | minutes over which each macro move is measured |
| `macro.max_age_seconds` | 180 | a macro price older than this is not live |
| `macro.dollar_full_pct` / `usdinr_full_pct` / `crude_full_pct` / `gold_full_pct` | 0.15 / 0.10 / 0.80 / 0.40 | % move that counts as full strength |
| `factors.<nifty, banknifty, gold, silver>.<factor>` | `on` | `off` leaves that factor out of that index's or metal's bias; flipped in Config → Factors, one version per flip |
| `macro.gift_full_pct` / `gift_fade_minutes` / `gift_direction` | 0.50 / 30 / `follow` | NIFTY's GIFT Nifty gap: overnight % at full strength, minutes it fades over, follow or fade the gap |
| `bias.entry_threshold` | 0.50 | \|bias\| to fire under `minute_close` |
| `bias.setup_threshold` | 0.35 | \|bias\| to set up under `trigger`; must be above the neutral band and no higher than the entry threshold |
| `bias.neutral_band` | 0.20 | below this the bias is Neutral, and an active signal is reversed |
| `bias.rearm_hysteresis` | 0.0 | 0 = off |
| `flow.window_seconds` | 15 | smoothing window for order flow |
| `flow.trigger_score` | 0.25 | flow score needed to fire a trigger signal |
| `flow.hold_seconds` | 5 | how long it must hold |
| `flow.w_fut_book` / `w_fut_trades` / `w_options` | 0.4 / 0.3 / 0.3 | mix of the flow score; must sum to 1 |
| `signal.entry_mode` | `minute_close` | the live rule; the other runs in shadow |
| `signal.max_spread_pct` | 1.0 | widest spread a trigger signal accepts |
| `signal.signal_ttl_seconds` | 300 | time before an untraded signal lapses |
| `signal.target_pct` / `stop_pct` | 30 / −15 | normal-day target and stop |
| `signal.expiry_points.<INDEX>` | 40/20, 100/50 | expiry-day target and stop in index points |
| `signal.outcome_horizon_minutes` | 30 | how long each signal is scored for |
| `signal.last_signal_time` / `_expiry` | 15:00 / 13:00 | last time a signal may fire |
| `chain.strike_window` / `recenter_strikes` | 10 / 2 | strikes either side of the chain's centre, and how far spot moves before it re-centres (this decides the "ATM" strike, section 2) |
| `paper.square_off_time` | 15:15 | open index paper trades close |
| `paper.cost_per_trade` | ₹60 | round-trip cost per lot |
| `paper.lots` | 1 | lots per paper trade |

The `[trend]`, `[oi]` and `[premium]` tables hold the periods and full-strength values
quoted in section 3. The `bullion` section is in 13.10.

---

## 12. Where the code is

| Part | File |
|---|---|
| Indicators (pure maths) | `backend/tradedisha/indicators/trend.py`, `oi.py`, `premium.py`, `macro.py`, `gift.py`, `series.py`, `greeks.py` |
| Macro data: currency and crude contracts, candles, the evidence view | `backend/tradedisha/market/macro.py` (`MacroTracker`, `build_view`) |
| GIFT Nifty's overnight reading: fetch and store | `backend/tradedisha/market/gift.py` (`GiftNifty`), `store/gift.py` |
| Combining votes into the bias | `backend/tradedisha/engine/aggregator.py` |
| Running indicators each minute, storing the bias | `backend/tradedisha/engine/bias_engine.py` |
| Order-flow score | `backend/tradedisha/market/flow.py` |
| Entry rules, gates, target and stop, signal life cycle | `backend/tradedisha/engine/signals.py` |
| Live levels while a signal waits | `engine/signals.py` (`rescale_levels`, `SignalEngine.live`), `api/signals.py` (`live_out`), the `signal_live` frame in `api/ws.py` |
| Outcomes and the scorecard | `backend/tradedisha/engine/outcomes.py` |
| Wiring (live and shadow engines, flow, outcomes) | `backend/tradedisha/market/session.py` |
| Option chain, build-up, PCR, max pain | `backend/tradedisha/market/chain.py` |
| Parameters | `backend/tradedisha/parameters/model.py` (the fields), `parameters/service.py` (versions), `config/params.toml` (starting values) |
| Tests | `backend/tests/test_signals.py`, `test_outcomes.py`, `tests/market/test_flow.py`, `tests/indicators/` |

---

## 13. Bullion signals: gold and silver

> **Note: terms used in this section**
>
> - **MCX**: Multi Commodity Exchange of India, where gold and silver futures trade. It is a
>   different exchange from NSE, open 09:00 to 23:30 IST (23:55 while the US is on
>   standard time), with its own holidays.
> - **Future (here)**: a contract to buy or sell 1 kg of gold or 30 kg of silver on a later
>   date at today's agreed price. Unlike an option it gains and loses one-for-one with the
>   metal's price, in either direction.
> - **Near month**: the future with the nearest expiry strictly after today. It is the most
>   traded, and TradeDisha switches (**rolls**) to the next one on expiry day.
> - **Long / short**: buying (gains when the price rises) or selling (gains when it falls).
>   `BUY_FUT` is a long signal, `SELL_FUT` a short one.
> - **Point value** (`qty_multiplier`): rupees gained or lost per one-rupee move in the
>   quoted price, per lot. GOLD is quoted per 10 g but a lot is 1 kg, so **₹100**; SILVER is
>   quoted per kg on a 30 kg lot, so **₹30**.
> - **Bullion live**: the feed is connected, MCX is open and a gold or silver tick has
>   arrived in the last 15 seconds. It is judged apart from the index feed.

The bullion engine is a smaller, separate copy of the pipeline above, run by
`BullionDesk` (`engine/bullion_desk.py`). It shares the candle maths, the trend
indicators, the aggregator and the signal and trade tables with the index engine, and
nothing else: no index bias, signal or trade ever reads bullion, and bullion never reads
the option chain, order flow or NSE hours.

```
MCX GOLD / SILVER ticks ─> BullionTracker (its own 1-minute candles)
        │                          │ candle closes
        │                          v
        │          queued; worked out 20 s after the minute closes
        │                          │
        │                          v
        │   trend, futures OI, order flow, other markets ─> bias (−1..+1) ─> gates ─> BUY_FUT / SELL_FUT
        │                                                         │
        └──────────── live price ─────────────────────> live levels, paper trade
```

### 13.1 How it differs from the index engine

| | Index (NIFTY, BANK NIFTY) | Bullion (GOLD, SILVER) |
|---|---|---|
| What a signal trades | buy the ATM call or put | buy or sell the near-month future |
| Evidence | 9 indicators: trend, OI, premium; plus macro (dollar, USD/INR, crude, gold) | 3 trend votes; the future's OI build-up; order flow (net volume, the book's lean); the dollar, USD/INR and the other metal's trend (there is no option chain) |
| Candles the trend reads | spot (EMAs, supertrend), future (VWAP) | the near-month future for all three |
| Order flow | read at the trigger (section 5), not in the bias | two votes in the bias, the `flow` group (E13) |
| When it is worked out | at the minute close | 20 s after the minute close |
| Entry threshold | \|bias\| ≥ 0.50 | \|bias\| ≥ 0.60 |
| Entry rules | `minute_close` and `trigger`, with a shadow engine | `minute_close` only, no shadow |
| Signal hours | 09:15 to 15:00 (13:00 on expiry day), NSE days | 09:15 to 22:45, MCX open |
| Target / stop | +30 % / −15 % of the option premium, or index points on expiry day | ±0.40 % / 0.20 % of the future's price |
| Square-off | 15:15 | 23:00 |
| Scored by the outcome yardstick | yes | no (it measures NSE spot moves) |

### 13.2 Inputs

> **Note:** a **contract roll** is the switch from the expiring future to the next one.

For each metal, from the MCX instrument file of the day:

| Input | Built from | Used for |
|---|---|---|
| Near-month candles | the near contract's ticks, 1-minute bars, kept for 900 minutes (a full MCX day) | all three indicators |
| VWAP | running close × volume over those candles, from the day's first candle | `vwap_position` |
| Latest tick | the near contract | entry price, live levels, paper-trade fills |
| Signed volume | each candle's buy and sell volume (E8). None for backfilled minutes; a volume jump after more than 30 s of silence is counted but not signed | `net_volume` |
| Per-minute OI and book | the near contract as it stood at the end of each minute (its last tick): OI, total buy and sell quantity, five-level bid and ask quantity; kept 900 minutes | `futures_oi`, `book_imbalance` (E13) |
| The other metal's candles | its near-month future, up to the same minute | `peer_metal` (E13) |
| Next-month price | the next contract | display only (calendar spread) |
| Dollar-index proxy, USD/INR | NSE currency futures, as for the indices (section 3.4) | the macro group, from E12 |

At start the live feed backfills today's 1-minute candles from 09:00, so the indicators
are not cold. A bullion candle closes on the first tick of the next minute, or 2 seconds
after the minute ends if no tick comes. These candles live in the tracker's own builder
and are stored under the MCX key; they never reach the index candle builder.

### 13.3 Step 1: the indicators vote

> **Note: terms used here**
>
> - **Open interest (OI)**: futures contracts still open. It rises when a new buyer meets
>   a new seller and falls when both sides close.
> - **Build-up**: OI rising with a move, so new positions are behind it. **Long build-up**:
>   price up, OI up. **Short build-up**: price down, OI up. **Short covering**: price up,
>   OI down (sellers buying back). **Long unwinding**: price down, OI down.
> - **Book lean**: (buy − sell) / (buy + sell) of the quantity waiting in the order book,
>   −1..+1.

There are four groups. The trend indicators are the same functions, with the same
settings, as the index trend group (section 3.1); only the candles differ: here every
input is the gold or silver near-month future.

**Trend** (`trend`):

| Indicator | What it measures | Score |
|---|---|---|
| `ema_cross` | Gap between EMA 9 and EMA 21 of the future's closes, as % of the slow EMA | `tanh(8 × gap%)`. A gap of +0.10 % scores about +0.66. Needs 21 bars. |
| `vwap_position` | The future's last close against its VWAP, in % | `clamp(distance% / 0.3)`. 0.3 % above VWAP is full strength. |
| `supertrend` | Side of the supertrend line (period 10, multiplier 3) the price is on | +1 above, −1 below, ramped over 3 bars after a flip. Needs 11 bars. |

**Positioning** (`oi`, Milestone E13):

| Indicator | What it measures | Score |
|---|---|---|
| `futures_oi` | The future's price change against its OI change over 15 minutes (`oi_window_minutes`) | Strength `clamp(\|OI change %\| / 0.50)` (`oi_full_pct`), in the price's direction. Build-up counts fully, covering and unwinding half (`oi_unwind_factor`). A price move under 0.02 % (`oi_price_flat_pct`) or unchanged OI scores 0. Warms until 16 minutes of readings, and across a feed gap (no reading within 5 minutes of 15 minutes back). |

**Order flow** (`flow`, Milestone E13):

| Indicator | What it measures | Score |
|---|---|---|
| `net_volume` | Buyer- less seller-initiated volume over the last 15 candles (`flow_window_minutes`), as a share of the signed volume | `clamp(share / 0.50)` (`flow_trades_full`). Warms until 15 live minutes (backfilled ones have no sides); nothing traded scores 0. |
| `book_imbalance` | The book lean now (mean of the total-quantity and five-level leans) against its average over the last 30 readings (`flow_book_minutes`) | `clamp((lean − average) / 0.20)` (`flow_book_full`). MCX books lean one way for hours (silver's pending sell quantity often runs well above its buy quantity), so only a change in the lean counts. Warms until 30 readings. |

**Other markets** (`macro`): `dollar_index` and `usd_inr` as in section 3.4, and from E13:

| Indicator | What it measures | Score |
|---|---|---|
| `peer_metal` | The other metal's trend: SILVER's for GOLD, GOLD's for SILVER | the mean of its `ok` trend votes, up to the same minute. Its trend, not its bias, so neither metal reads itself. |

Only candles and readings up to and including the minute being worked out are used, even
though the evaluation runs 20 seconds into the next minute.

### 13.4 Step 2: the votes become one bias

> **Note:** the group weights come from `bullion_weights()`: OI 0.15
> (`bullion.oi_weight`), flow 0.15 (`bullion.flow_weight`), other markets 0.10
> (`bullion.macro_weight`), and trend the rest, 0.60. The dollar readings for bullion are
> `dollar_index` with a minus sign (a strong dollar pushes gold down) and `usd_inr` with a
> **plus** sign: MCX prices are world prices × USD/INR, so a weaker rupee lifts them.

`aggregate()` is the same function as for the indices, given those weights, the bullion
neutral band and the bullion idle groups:

1. **Group score** = the average of the group's indicators whose quality is `ok`. Warming
   ones are left out, not counted as zero.
2. **Idle groups.** An OI, flow or macro group with no `ok` reading gives its share to the
   live groups in proportion to theirs. At start (backfilled candles have no OI, book or
   sides) the bias is trend alone until the new votes warm up; after 17:00, when the
   currency market shuts, the other metal carries the macro share alone.
3. **Bias** = the weighted sum of the group scores, clamped to −1..+1.
4. **Label**: ≥ +0.20 Bullish, ≤ −0.20 Bearish, otherwise Neutral (`bullion.neutral_band`).
   Strength is `round(|bias| × 100)`.

Trend still carries most of the bias and there is no option chain to temper it, so a
bullion bias swings further than an index bias. That is why its entry threshold is
higher, 0.60 against 0.50.

**Worked example** (GOLD, replayed from the recording of 18/11/2026 at 21:46; the replay
had no currency prices, so macro is the other metal alone):

| Group (weight) | Indicator | Reading | Score |
|---|---|---|---|
| trend (0.60) | `ema_cross` | EMA 9 below EMA 21 by 0.08 % | −0.56 |
| | `vwap_position` | future below VWAP by 0.49 % | −1.00 |
| | `supertrend` | price below supertrend for 18 bars | −1.00 |
| oi (0.15) | `futures_oi` | short build-up: price −0.03 %, OI +0.23 % in 15 min | −0.47 |
| flow (0.15) | `net_volume` | net selling 2 % of 143 traded in 15 min | −0.04 |
| | `book_imbalance` | book lean +0.09 against +0.06 over 30 min | +0.13 |
| macro (0.10) | `peer_metal` | SILVER trend −0.95 | −0.95 |

Group scores: trend (−0.56 − 1.00 − 1.00) / 3 = −0.85, OI −0.47, flow (−0.04 + 0.13) / 2 =
+0.04, macro −0.95. Bias = 0.60 × −0.85 + 0.15 × −0.47 + 0.15 × 0.04 + 0.10 × −0.95 =
**−0.67**: Bearish, strength 67, above 0.60, so a short (`SELL_FUT`) fires.

Each minute's bias is stored in `bias_minutes` under `GOLD` or `SILVER`, with its full
breakdown, and shown in the Market view and Evidence panels of the BULLION tab.

### 13.5 When it is worked out: the 20-second offset

> **Note:** the **offset** (`bullion.eval_offset_seconds`, default 20, range 0–50) is how
> long after a minute closes the bullion bias and signal are worked out.

The index engines run at the minute close, where their latency budget is measured. So that
bullion never competes with them for the same instant, a bullion candle close only
**queues** the minute with a due time of `minute start + 60 s + offset`. The queue is
checked on every bullion tick and twice a second, on the market clock. A minute is
evaluated once, when its due time has passed. In replay the market clock follows the
recorded ticks, so a replayed signal fires at the same moment it did live. A changed offset
applies from the next minute queued. The actual delay is recorded as the latency hop
`bullion_eval_lag`.

The signal then carries two times: `minute_ts`, the minute evaluated, and `ts_fired`, the
evaluation instant (about 20 s after that minute closed). The entry price and the TTL
come from `ts_fired`.

### 13.6 Step 3: the gates

At each evaluation `BullionSignalEngine.on_bias()` first lapses an expired signal, checks
for a reversal (13.8) and does the re-arm bookkeeping, as in section 6.1. It then checks,
in order, and the first failure is the reason shown on the card:

| # | Gate | Reason code if it fails |
|---|---|---|
| 1 | Bullion signals are on (`bullion.signals`) | `disabled` |
| 2 | \|bias\| ≥ `bullion.entry_threshold` (0.60) | `below_threshold` |
| 3 | No signal is active on this metal | `active_exists` |
| 4 | Not blocked by re-arm (`bullion.rearm_hysteresis`, off by default) | `rearm` |
| 5 | MCX is open, and the time is from `first_signal_time` (09:15) to before `last_signal_time` (22:45) | `outside_hours` |
| 6 | Bullion is live (connected, MCX open, a bullion tick in the last 15 s) | `feed_down` |
| 7 | The near future has a price | `no_price` |

Direction is the sign of the bias: positive fires `BUY_FUT`, negative fires `SELL_FUT`.
GOLD and SILVER are independent: each has its own bias, active signal and gates. Hours
are enforced on the live and replay feeds; there is no bullion on the synthetic feed.

The index feed plays no part: an NSE outage does not stop bullion signals, and a bullion
outage does not put the index engines into degraded mode.

### 13.7 Step 4: building the signal

> **Note:** the **mid price** is halfway between the best bid and the best ask.

**Entry** is the near future's last traded price at the evaluation instant.

**Target and stop** are percentages of the entry, on the signal's side:

| | Long (`BUY_FUT`) | Short (`SELL_FUT`) |
|---|---|---|
| Target | entry × (1 + 0.40 %) | entry × (1 − 0.40 %) |
| Stop | entry × (1 − 0.20 %) | entry × (1 + 0.20 %) |

(`bullion.target_pct = 0.40`, `bullion.stop_pct = 0.20`, both rounded to the paisa.) That is
risking 1 to make 2, as with the index options.

**Examples, one lot:**

| | GOLD long | SILVER short |
|---|---|---|
| Entry | ₹1,35,000 per 10 g | ₹1,70,000 per kg |
| Target | ₹1,35,540 (+540) | ₹1,69,320 (−680) |
| Stop | ₹1,34,730 (−270) | ₹1,70,340 (+340) |
| Point value | ₹100 | ₹30 |
| Gross at target | +₹54,000 | +₹20,400 |
| Gross at stop | −₹27,000 | −₹10,200 |
| Cost (13.9) | ₹3,300 | ₹1,284 |

**What the signal records** (the same `signals` table as the indices):

| Field | Bullion value |
|---|---|
| `index` | `GOLD` or `SILVER` |
| `direction` | `BUY_FUT` or `SELL_FUT` |
| `trading_symbol`, `expiry` | the near-month future, e.g. `GOLD FUT 04 DEC 26` |
| `strike` | 0 (a future has none) |
| `lot_size` | the point value: 100 for GOLD, 30 for SILVER |
| `entry_price`, `target_price`, `stop_price` | as above |
| `target_basis` | `pct` |
| `entry_ask`, `spread_pct` | the ask for a long or the bid for a short, and the spread as % of mid, when the feed sends a quote |
| `entry_mode`, `shadow` | always `minute_close`, `false` |
| `bias`, `strength`, `breakdown_json`, `config_version` | as for the indices |
| `expires_at` | `ts_fired` + `bullion.signal_ttl_seconds` (300 s) |

**Live levels.** While the signal waits, the card shows the fired levels and the live
ones: the same ratios applied to the future's price now (for the short above, at
₹1,69,000 the live target is ₹1,68,324 and stop ₹1,69,338).

### 13.8 Step 5: how a bullion signal ends

The same three endings as section 8:

| Ending | When |
|---|---|
| `traded` | you open a paper trade from it |
| `lapsed` | 300 s pass since it fired (checked at each evaluation and twice a second) |
| `reversed` | at an evaluation the bias has the opposite sign, or \|bias\| < 0.20 |

### 13.9 Paper trades on bullion

> **Note:** **CTT** (Commodity Transaction Tax) is charged on the sale value of commodity
> futures; with exchange charges, stamp duty and GST it scales with the value traded.

- **Opening** is refused unless MCX is open, the time is before the 23:00 square-off and
  bullion is live. The trade fills at the future's price at your click, with the live
  target and stop at that price.
- **Quantity** = point value × lots (`bullion.lots`, default 1).
- **P&L** = side × (exit − entry) × quantity, where side is +1 for a long and −1 for a
  short.
- **Exits**: target, stop (mirrored for a short: its target is below the entry), the
  23:00 square-off on the MCX clock (`bullion.square_off_time`), or by hand.
- **Cost**, fixed at entry: `cost_fixed_per_lot × lots + cost_pct_of_value / 100 × entry
  × quantity × 2` = ₹60 per lot + 0.012 % of the round-trip value. A GOLD lot at
  ₹1,35,000 is worth ₹1.35 crore, so 60 + 0.012 % × 2.7 crore = **₹3,300**.
- A separate paper-trade manager owns bullion trades, so they square off on MCX time and
  survive a restart without touching the index trades. In the Journal they appear as
  GOLD, SILVER and a Bullion total; "Index options" (the overall line) leaves them out.

### 13.10 Bullion parameters

All in the `bullion` section of the config editor:

| Parameter | Default | Effect |
|---|---|---|
| `bullion.signals` | `on` | `off` stops bullion signals (gate `disabled`) |
| `bullion.entry_threshold` | 0.60 | \|bias\| to fire |
| `bullion.neutral_band` | 0.20 | below this the bias is Neutral, and an active signal is reversed |
| `bullion.rearm_hysteresis` | 0.0 | 0 = off |
| `bullion.signal_ttl_seconds` | 300 | time before an untraded signal lapses |
| `bullion.eval_offset_seconds` | 20 | seconds after the minute close the bias and signal run |
| `bullion.first_signal_time` / `last_signal_time` | 09:15 / 22:45 | signal hours |
| `bullion.square_off_time` | 23:00 | open bullion paper trades close |
| `bullion.target_pct` / `stop_pct` | 0.40 / 0.20 | % of the future's price |
| `bullion.lots` | 1 | lots per paper trade |
| `bullion.cost_fixed_per_lot` / `cost_pct_of_value` | ₹60 / 0.012 % | paper-trade cost |
| `bullion.macro_weight` | 0.10 | other markets' share: the dollar (E12) and the other metal (E13) |
| `bullion.oi_weight` / `flow_weight` | 0.15 / 0.15 | the futures OI and order-flow shares (E13); trend has what the three leave, and they must leave it some |
| `bullion.oi_window_minutes` | 15 | minutes over which price and OI changes are read |
| `bullion.oi_full_pct` | 0.50 | OI change (%) that is full strength |
| `bullion.oi_price_flat_pct` | 0.02 | a smaller price move (%) reads no build-up |
| `bullion.oi_unwind_factor` | 0.5 | how much covering and unwinding count against new positions |
| `bullion.flow_window_minutes` | 15 | minutes of signed volume behind `net_volume` |
| `bullion.flow_trades_full` | 0.50 | net volume share that is full strength |
| `bullion.flow_book_minutes` | 30 | the readings the book's usual lean is averaged over |
| `bullion.flow_book_full` | 0.20 | lean above that average that is full strength |

The E13 weights and full-strength values are starting values. Replaying the 2.5 recorded
MCX sessions (16–18/11/2026) cut bullion signals from 168 to 80: better on SILVER
(+0.10 % per signal against +0.04 %), worse on GOLD (−0.02 % against +0.04 %). That is
too little data to judge, so they are to be tuned once some weeks are recorded.

The indicator periods come from the `[trend]` table, shared with the indices. MCX hours
and holidays are process settings (`mcx_open`, `mcx_close`, `config/mcx-holidays.txt`), not
parameters.

### 13.11 Where the bullion code is

| Part | File |
|---|---|
| Contracts, ticks, candles, day range | `backend/tradedisha/market/bullion.py` (`BullionTracker`) |
| Bias and the offset queue | `backend/tradedisha/engine/bullion_bias.py`; the dollar and the other metal from `indicators/macro.py` (`bullion_macro_indicators`, `peer_metal`) |
| Futures OI build-up, net volume, book lean | `backend/tradedisha/indicators/futures.py`; the per-minute readings from `BullionTracker.minute_book()` |
| Group weights and idle groups | `backend/tradedisha/engine/aggregator.py` (`bullion_weights`, `BULLION_IDLE`) |
| Gates, building the signal, its life cycle, live levels | `backend/tradedisha/engine/bullion_signals.py` |
| Bias, signals and paper trades wired together | `backend/tradedisha/engine/bullion_desk.py` |
| Side-aware P&L, bullion cost and square-off rules | `backend/tradedisha/engine/paper.py` (`bullion_rules`) |
| Bullion liveness, recording, replay | `backend/tradedisha/market/session.py` |
| Tests | `backend/tests/test_bullion_trading.py`, `test_live_levels.py`, `tests/market/test_bullion_replay.py`, `tests/indicators/test_futures.py` |

