# How the signal engine works

This document explains, end to end, how TradeDisha decides to raise a "buy call" or "buy
put" signal: what data goes in, how it becomes a single bias number each minute, the two
entry rules, how targets and stops are set, how a signal ends, and how every signal is
scored afterwards.

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
raises a signal to buy the call or the put nearest the current index level.**

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

The indicators are in three groups of three. They are pure functions in
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

| Group | Normal weight | Expiry-day weight |
|---|---|---|
| Trend | 0.40 | 0.508 |
| OI | 0.35 | 0.175 |
| Premium | 0.25 | 0.317 |

On expiry day OI is distorted by positions being closed, so its weight is halved
(`expiry_oi_weight_factor = 0.5`) and the share it gives up is handed to the other two in
proportion to their own weights.

**3. Sum and clamp.** `bias = Σ (group weight × group score)`, clamped to −1..+1.

**4. Label.** With a neutral band of 0.20: bias ≥ +0.20 is **Bullish**, ≤ −0.20 is
**Bearish**, otherwise **Neutral**. Strength is `round(|bias| × 100)`.

**Worked example** (a normal day, all indicators ready):

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

**Degraded feed.** If ticks stop for more than 5 seconds during market hours, the feed is
not live: no signal fires (`feed_down`), paper-trade entry and manual close are refused,
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

Every signal, live or shadow, traded or not, and however it ended, is followed by
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

Each signal records the version in force when it fired (`config_version`). It appears as
a small `v7` on the signal card and in "Signals today"; hovering it shows that version's
values and highlights the ones that differ from the current config.

| Parameter | Default | Effect |
|---|---|---|
| `weights.trend` / `oi` / `premium` | 0.40 / 0.35 / 0.25 | group shares of the bias; must sum to 1 |
| `weights.expiry_oi_weight_factor` | 0.5 | OI weight multiplier on expiry day |
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

The `[trend]`, `[oi]` and `[premium]` tables hold the periods and full-strength values
quoted in section 3.

---

## 12. Where the code is

| Part | File |
|---|---|
| Indicators (pure maths) | `backend/tradedisha/indicators/trend.py`, `oi.py`, `premium.py`, `series.py`, `greeks.py` |
| Combining votes into the bias | `backend/tradedisha/engine/aggregator.py` |
| Running indicators each minute, storing the bias | `backend/tradedisha/engine/bias_engine.py` |
| Order-flow score | `backend/tradedisha/market/flow.py` |
| Entry rules, gates, target and stop, signal life cycle | `backend/tradedisha/engine/signals.py` |
| Outcomes and the scorecard | `backend/tradedisha/engine/outcomes.py` |
| Wiring (live and shadow engines, flow, outcomes) | `backend/tradedisha/market/session.py` |
| Option chain, build-up, PCR, max pain | `backend/tradedisha/market/chain.py` |
| Parameters | `backend/tradedisha/parameters/model.py` (the fields), `parameters/service.py` (versions), `config/params.toml` (starting values) |
| Tests | `backend/tests/test_signals.py`, `test_outcomes.py`, `tests/market/test_flow.py`, `tests/indicators/` |
