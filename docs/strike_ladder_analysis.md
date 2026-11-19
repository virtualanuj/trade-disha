# Strike ladder: signals for ATM ±3 strikes

Analysis, 2026-11-17. What it would take for the signal engine to recommend, and score,
options from three strikes in the money to three out of the money, instead of the ATM
strike alone: complexity, performance and data needs. Nothing here is built.

**In short:** the data is already subscribed and recorded, and performance is not a
concern. The work is plumbing, because everything after the signal decision assumes one
option per signal.

## How a signal is worked out today

```
ticks → candles + option chain (±10 strikes) → bias per index per minute (one number)
      → SignalEngine: gates (threshold, one active per index, hours, feed live,
        re-arm; trigger mode adds flow hold + spread)
      → _fire(): picks chain.rows[chain.atm] → CE or PE → entry, target, stop
      → stored (signals) → OutcomeTracker scores that one option
      → signal card / signal_live (1/s) → paper trade buys that option
```

- **The strike plays no part in the decision.** Bias, direction, gates, lapse and
  reversal are all index-level.
- **The strike comes in at one point:** `engine/signals.py` `_fire()` and the
  trigger-mode `_quote_gate()` both take `chain.rows.get(chain.atm)`.
- **Everything after that assumes one option per signal:**
  - The `signals` row has a single `instrument_key`, `strike`, entry, target and stop.
  - `engine/outcomes.py:OutcomeTracker` follows that one key.
  - `SignalEngine.live()` and `levels_at()` read that one leg.
  - `engine/paper.py:PaperTradeManager.open(signal_id)` buys `signal.instrument_key`.
  - The signal card shows one option.

So signals for ATM ±3 cannot mean seven separately decided signals: all seven would fire
at the same instant for the same reason. It can only mean **one decision, offered across
seven strikes**.

## Three ways to build it

| | What it is | Size |
|---|---|---|
| **A. Strike ladder (recommended)** | One signal, as now, carrying 7 legs (ATM −3…+3). Each leg has its own entry, target, stop, delta and spread, live levels and outcome score. The trader chooses the strike when paper trading. | Medium-large, about an E10-size milestone |
| B. Strike offset setting | A parameter `signal.strike_offset` (−3…+3) makes the engine pick that strike instead of ATM. Still one option per signal. | Small |
| C. Independent signals per strike | 7 signals with their own lifecycles | Not recommended: the same decision 7 times, breaks "one active signal per index", clutters the journal and scorecard |

A's real payoff is the scorecard. Every signal is scored on all 7 strikes at once, so
within days it shows which strike would have worked best. With B that is only learned by
switching the setting and waiting.

## Data needs

**Already available, no new subscriptions:**

- **Coverage:** the chain subscribes ±10 strikes in full mode (LTP, bid/ask, OI, IV, and
  delta from the feed's option Greeks).
- **After a re-centre:** the chain re-centres when spot moves 2 strikes (the process
  setting `TRADEDISHA_RECENTER_STRIKES`; the `chain.recenter_strikes` parameter is not
  read), so a leg at offset ±3 sits at most about 5 strikes from the
  centre, still inside the window.
- **History:** every strike in the window is recorded in `ticks` (114 option keys on
  2026-11-17). The replay scorer (`tools/score.py`) can therefore backtest the ladder on
  days already recorded.

**Measured on 2026-11-16** (NIFTY and BANK NIFTY, sampled every 15 s through the
session). Offset is in moneyness: negative is in the money, positive is out of the money,
the same for calls and puts.

| NIFTY offset | −3 | −2 | −1 | 0 | +1 | +2 | +3 |
|---|---|---|---|---|---|---|---|
| median premium | 191 | 156 | 124 | 96 | 73 | 55 | 41 |
| \|delta\| | 0.73 | 0.66 | 0.58 | 0.50 | 0.42 | 0.34 | 0.27 |
| spread % (p50 / p90) | 0.24/0.27 | 0.23/0.27 | 0.24/0.28 | 0.24/0.29 | 0.25/0.31 | 0.26/0.35 | 0.30/0.39 |

- **BANK NIFTY:** similar, with deltas from 0.58 to 0.42 and spreads under 0.41 % at p90.
- **Liquidity:** no strike was ever over the 1 % spread gate (`signal.max_spread_pct`),
  so every offset is tradable on a normal day.
- **Caveat:** this is one non-expiry day. Out-of-the-money spreads usually widen on expiry
  day, and that has not been measured yet.

**Gaps that need a decision, not more data:**

1. **What "ATM" means for the ladder.** The engine's ATM is the chain centre, which can be
   up to about 2 strikes from the true nearest strike (`docs/signal.md`, "Which strike is
   'ATM' here"). The ladder should be centred on the true ATM from spot at fire time, or
   "+3 out of the money" can really be +5.
2. **The target and stop rule per strike.** On normal days target and stop are a fixed %
   of premium (`signal.target_pct`, `signal.stop_pct`). The same % means very different
   index moves across the ladder: +3's delta of 0.27 needs a much bigger index move to
   make the same % than −3's 0.73. For the scores to be comparable, normal days should use
   what expiry day already uses: index points × each leg's delta. That rule already exists
   in `_fire()` and `rescale_levels()`. This is the most important design decision.
3. **The trigger-mode spread check.** Check only the primary leg, or mark each leg
   tradable or not by its own spread.
4. **Shadow signals.** Ladder them too, which doubles the tracking, or keep them on ATM
   only.
5. **A known risk, worse with more strikes:** if spot runs about 7 strikes (around 350
   NIFTY points) within the 30-minute scoring horizon, an outer leg can leave the
   subscribed window and stop updating. The fix is to keep active signals' and open
   trades' keys subscribed.

## What changes for option A

| Area | Change | Size |
|---|---|---|
| `engine/signals.py` | Pull leg pricing (entry, delta, target and stop) out of `_fire()` and run it for 7 strikes; `live()` and `levels_at()` work per leg; the spread check per leg | M |
| Migration 015 (the next free number) | A new `signal_legs` table (signal_id, offset, strike, key, entry, target, stop, delta, spread). The `signals` row keeps the ATM leg so the journal, old data and the scorecard keep working | S |
| `engine/outcomes.py` | Track (signal, offset) pairs; outcomes keyed by leg (a new table or a `leg` column); look trackers up by instrument key instead of looping over all of them | M |
| `engine/paper.py`, `api/paper.py` | `open(signal_id, offset=0)`: buy the chosen leg at its live levels | S |
| `tools/score.py` and the scorecard | Results per offset (hit rate, best and worst, late share), which is the point of the exercise | M |
| API and WS | `SignalOut.legs`; `signal_live` carries 7 legs | S |
| Frontend | Signal card gets a strike-ladder table (strike, moneyness, live LTP, target, stop, delta, spread, a Paper trade button per row); scorecard by offset | M-L |
| `ParameterSet` | `signal.ladder_offsets` (default 0, or −3…+3) and the per-strike target rule | S |
| Docs | spec §9, signal.md, plan, enhancements | S |

**Option B** is small: one parameter, `_fire()` and the spread check picking
`atm + offset × step` (from the true ATM), plus docs and tests. Nothing downstream
changes, because it is still one option per signal.

## Performance

- **At fire time:** 7 legs × (a dictionary lookup plus at most one Black-Scholes delta) is
  microseconds, against the 100 ms signal budget (spec §14a).
- **Outcome tracking:**
  - **Load:** the feed averaged 92 ticks/s on 2026-11-16, peaking at 219/s. About 80
    signals a day (live and shadow) with a 30-minute horizon means around 7 open trackers
    now, about 50 with the ladder.
  - **Cost:** the current loop over all trackers on every tick would be about 10,000
    checks/s at peak, roughly 1 % of a CPU core. With a lookup by instrument key it is one
    check per tick.
- **Database:** about 560 leg rows and outcomes a day instead of 80; outcome writes are
  already batched. Negligible.
- **WebSocket:** `signal_live` goes from 1 leg to 7 per active signal per second, about 1
  to 2 kB. Negligible.
- **Feed:** no change. The strikes are already subscribed and recorded.

## Suggested order

1. **Backtest offline first.** Extend `tools/score.py` to score ATM −3…+3 for every
   recorded signal on the days already recorded, using the delta-scaled target and stop.
   It needs no UI and no schema change, and it shows whether any non-ATM strike beats ATM
   before the app is changed.
2. If one offset clearly wins, **option B** may be all that is needed.
3. If the choice is wanted at each trade, build **option A**.

Decisions needed before planning: which option (A, B, or the backtest first), and whether
normal-day targets switch to the delta-scaled rule for non-ATM strikes.
