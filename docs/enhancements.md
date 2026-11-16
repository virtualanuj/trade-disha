# TradeDisha — Enhancements

Improvements requested after release 1.0.0. This is the running list. Items that have been
specified point to where the requirement, the design and the milestone live.

## UI

### 1. Resizable panels

Make the panels resizable.

Status: built in Milestone E1, awaiting the manual test. Requirement in [intent.md](intent.md) ("Enhancements after
the first version"); design in [spec.md](spec.md) §13.2 "Resizable layout"; planned in
[plan.md](plan.md) Milestone E1.

Decided in the spec: two draggable dividers (main column / option chain, and under the
price chart), with size limits, double-click to reset, and sizes remembered in the browser.

### 2. Collapsible right-hand panel

Make the right-hand panel collapsible (show/hide).

Status: built in Milestone E1, awaiting the manual test. Design in spec §13.2 "SidePanel".

Decided in the spec: shown by default, the choice remembered in the browser. Hidden, a
narrow strip on the right edge brings it back at its previous width. The option chain
keeps updating behind the scenes, so the market view and signals are unaffected.

Since Milestone E2 the hide control is the option-chain panel's minimise button (item 5);
the strip and the remembered choice are unchanged.

### 3. DD/MM/YYYY date format

Use DD/MM/YYYY for dates on the UI.

Status: built in Milestone E1, awaiting the manual test. Design in spec §13.3 "Dates"; planned in Milestone E1.

Decided in the spec: display only. The API, the config file and file names keep ISO
dates. Native date pickers follow the browser's locale and are left alone.

### 4. Collapsible details in the index top panel

Enhance the NIFTY top panel with a collapsible details view showing:

- the day's open, high and low, and where the price sits in the day's range
- the 52-week high and low
- previous close, and change and change % on the day
- futures premium over spot
- India VIX

The same view applies to BANK NIFTY through the index tabs.

Status: built in Milestone E1, awaiting the manual test. Design in spec §7.4 (the statistics and their sources),
§6.2 and §6.5 (new data), §13.2 "IndexTiles"; planned in Milestone E1.

Data sources, confirmed against the Upstox documentation on 2026-11-13:
- Upstox has no 52-week high/low field, on the feed or in the quote API. It is computed
  from one year of daily candles
  (`GET /v3/historical-candle/{key}/days/1/{to_date}/{from_date}`), one request per index
  at start, then widened by today's high and low.
- India VIX is available as `NSE_INDEX|India VIX`.
- Still to check on the live feed (spec §17): that the computed 52-week figures match
  NSE's, and that VIX ticks on the websocket like the other indices.

### 5. Minimisable panels

Asked for: view one panel full screen, restore it to the original layout, or minimise it
to make room for the others. Full screen was built and then dropped at the owner's
request (2026-11-13); minimise-in-place is what remains.

Status: built in Milestone E2, awaiting the manual test on a live or replayed day.
Requirement in [intent.md](intent.md); design in [spec.md](spec.md) §13.2 "PanelFrame";
planned in [plan.md](plan.md) Milestone E2.

Decided with the owner on 2026-11-13:
- All eight panels get the same control: index, market view, signal, open paper trades,
  price chart, evidence, signals today, option chain.
- Minimise collapses a panel to its title bar where it sits, with a one-line summary; the
  panels below move up. Remembered in the browser.
- A minimised signal card or open-trades panel opens itself for a new signal or a newly
  opened trade, then stays down if minimised again until the next new one.
- The open paper trades panel is always on the page, even with none open, and sits
  second last in the main column, just above signals today.
- Built as one shared panel frame with no new library.

Not included: full screen for a panel; dragging panels to re-order them (re-ordering
with buttons is item 5a).

### 5a. Re-ordering the main column

Asked for (2026-11-16): move the panels in the left view up and down.

Status: built in Milestone E3 and checked in a browser on the live feed. Design in
[spec.md](spec.md) §13.2 "Panel order"; planned in [plan.md](plan.md) Milestone E3.

Decided with the owner on 2026-11-16:
- Up and down buttons on each panel's title bar, beside minimise. No drag-and-drop and no
  new library.
- Market view and signal are a pair: moving either moves both, so they stay side by side.
- The order is remembered in the browser, and "Restore panels" puts it back.
- The index tabs stay at the top and the option chain stays in its own column.

## Signals

### 6. Earlier signals with fewer false ones

Asked for (2026-11-13): on live and replayed days the signals are too often false (the
bias flips or the option goes nowhere) and too often late (most of the move is over).

Decided with the owner on 2026-11-13:
- Use the part of the Upstox feed the app was discarding: bid and ask quantities over the
  five book levels, total buy and sell quantity, the exchange average price and the last
  traded quantity.
- **Setup, then trigger.** The bias only sets the direction, at a lower bar. The signal
  fires inside the minute when order flow on the futures and the ATM options agrees and
  the option's bid-ask spread is tight.
- Measure before changing anything: every signal is scored by what its option did next,
  and the trigger first runs in shadow beside today's rule. It goes live only if the
  scores say it is better.

Considered and not chosen: order flow as a fourth evidence group in the bias (still fires
only at minute close, and averaging dilutes it); tuning persistence and thresholds on the
existing inputs (fewer false signals only by making them later).

Status: Milestones S1 (recording and scoring) and S2 (order-flow trigger in shadow) built,
awaiting a live day. S3 (switch on, on evidence) waits for at least five live sessions of
shadow data. Requirement in [intent.md](intent.md); design in [spec.md](spec.md) §6.2,
§8.5, §9.5, §9.6, §11, §12; milestones S1 to S3 in [plan.md](plan.md).

Not included: targets and stops sized from theta, gamma and vega; choosing a strike other
than ATM; the 30-level order book.

### 7. OI build-up vote reads the premium's direction

The ATM OI build-up vote counted any OI rise on a call as bearish and on a put as bullish,
as if all new OI were writing, so call buying in a rally voted bearish.

Decided with the owner on 2026-11-14: the textbook reading. The premium's direction
decides the side and the OI moved is the weight: a call whose premium rose is bullish, one
whose premium fell is bearish; a put is the mirror image. This matches the build-up badges
in the option chain.

Known and accepted: its sign now follows the premium's direction, so it overlaps with the
CE-vs-PE momentum vote. On the one recorded day (2026-11-13) neither the old nor the new
vote predicted the index's next 5 or 15 minutes, so this was decided on logic, not on
evidence; the scoring tool will say more as days accumulate.

Status: built. Design in [spec.md](spec.md) §8.2.

## Configuration

### 8. Editable, versioned config

Asked for (2026-11-16): edit the config in the app; version it with a number and a tag
the trader types; revert to an old version; keep it in a database table; link each signal
to its version and show the values on hover.

Status: built in Milestone C1 and checked in a browser on the synthetic feed. Design in
[spec.md](spec.md) §3.2 and §13.2; planned in [plan.md](plan.md) Milestone C1.

Decided with the owner on 2026-11-16:
- The database is the source of truth; `config/params.toml` only starts a new database
  off, and the "Reload config" button is gone.
- A revert saves the old values as a new version, so history is never rewritten.
- Each database (live, synthetic) has its own history, because a signal and its config
  version must be in the same database.
- Signals from before this change have no version.

Not included: a scorecard split by config version; comparing two versions side by side;
scoring a stored version with the offline tool.

## Market data

### 9. Bullion tab

Asked for (2026-11-16): pull gold and silver real-time prices from Upstox; then, make
bullion a tab like NIFTY and BANK NIFTY with the useful details Upstox already provides.

Status: built in Milestone E4, awaiting the live check. Design in [spec.md](spec.md)
§6.6 and §13.2; planned in [plan.md](plan.md) Milestone E4.

Decided with the owner on 2026-11-16:
- The MCX futures of GOLD (₹ per 10 g) and SILVER (₹ per kg), not the minis. Upstox has
  no spot price; these are what Indian markets quote, not the international dollar price.
- One BULLION tab with both metals side by side, the gold/silver ratio, and a chart with a
  metal switch; the option chain is hidden there.
- All of the details on offer:
  - day stats and liquidity
  - a 1-minute chart
  - the contract's range and circuit limits
  - the next month and calendar spread
- Display only: no signals or paper trades.

Builder's calls:
- The contract rolls on expiry day.
- Ticks and candles are not recorded (MCX trades until 23:30), so synthetic and replay
  have no tab.
- The day's OI high and low are left out: Upstox sends 0 for MCX.
- The previous close comes from the feed's `cp`, falling back to the quote's
  `last_price − net_change`.

## Deferred

### Chart zoom buttons

Zoom-in and zoom-out buttons on the charts. Left for now (decided 2026-11-13).

Notes:
- The chart is `frontend/src/components/PriceChart/PriceChart.tsx` (lightweight-charts).
- A "reset" or "fit the day" button alongside is worth considering when this is picked up.
