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

Not included: full screen for a panel; dragging panels to re-order them.

## Deferred

### Chart zoom buttons

Zoom-in and zoom-out buttons on the charts. Left for now (decided 2026-11-13).

Notes:
- The chart is `frontend/src/components/PriceChart/PriceChart.tsx` (lightweight-charts).
- A "reset" or "fit the day" button alongside is worth considering when this is picked up.
