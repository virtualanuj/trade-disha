# TradeDisha — Enhancements

Improvements requested after release 1.0.0. This is the running list. Items that have been
specified point to where the requirement, the design and the milestone live.

## UI

### 1. Resizable panels

Make the panels resizable.

Status: built in Milestone E1 and checked in a browser. Requirement in [intent.md](intent.md)
("Enhancements after the first version"); design in [spec.md](spec.md) §13.2 "Resizable
layout"; planned in [plan.md](plan.md) Milestone E1.

Decided in the spec: two draggable dividers (main column / option chain, and under the
price chart), with size limits, double-click to reset, and sizes remembered in the browser.

### 2. Collapsible right-hand panel

Make the right-hand panel collapsible (show/hide).

Status: built in Milestone E1 and checked in a browser. Design in spec §13.2 "SidePanel".

Decided in the spec: shown by default, the choice remembered in the browser. Hidden, a
narrow strip on the right edge brings it back at its previous width. The option chain
keeps updating behind the scenes, so the market view and signals are unaffected.

Since Milestone E2 the hide control is the option-chain panel's minimise button (item 5);
the strip and the remembered choice are unchanged.

### 3. DD/MM/YYYY date format

Use DD/MM/YYYY for dates on the UI.

Status: built in Milestone E1 and checked in a browser. Design in spec §13.3 "Dates";
planned in Milestone E1.

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

Status: built in Milestone E1 and checked on the live feed. Design in spec §7.4 (the
statistics and their sources), §6.2 and §6.5 (new data), §13.2 "IndexTiles"; planned in
Milestone E1.

Data sources, confirmed against the Upstox documentation on 2026-11-13:
- Upstox has no 52-week high/low field, on the feed or in the quote API. It is computed
  from one year of daily candles
  (`GET /v3/historical-candle/{key}/days/1/{to_date}/{from_date}`), one request per index
  at start, then widened by today's high and low.
- India VIX is available as `NSE_INDEX|India VIX`.
- Checked on the live feed (spec §17): the computed 52-week figures match NSE's, and VIX
  ticks on the websocket like the other indices.

### 5. Minimisable panels

Asked for: view one panel full screen, restore it to the original layout, or minimise it
to make room for the others. Full screen was built and then dropped at the owner's
request (2026-11-13); minimise-in-place is what remains.

Status: built in Milestone E2 and checked in a browser.
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
  *(Superseded by item 13: each now moves on its own.)*
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

Status: built in Milestone E4 and checked by the owner on the live feed (2026-11-16).
Design in [spec.md](spec.md) §6.6 and §13.2; planned in [plan.md](plan.md) Milestone E4.

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
- Display only: no signals or paper trades. *(Superseded by item 10, Milestone E6.)*

Builder's calls:
- The contract rolls on expiry day.
- Ticks and candles are not recorded (MCX trades until 23:30), so synthetic and replay
  have no tab. *(Superseded by item 10: bullion ticks now go to their own table, and a
  replay can include them.)*
- The day's OI high and low are left out: Upstox sends 0 for MCX.
- The previous close comes from the feed's `cp`, falling back to the quote's
  `last_price − net_change`.

### 9a. NSE and MCX hours apart

Found while checking item 9 on the live feed (2026-11-16): after 15:30 the feed pill went
red although bullion was ticking, the BULLION tab showed "Market closed", and gold ticks
kept the index feed counted as live, which would hide an index outage.

Status: built in Milestone E5 and checked on the live feed, including a network drop on
BULLION while MCX was open. Design in [spec.md](spec.md) §6.6 "Hours and liveness", §13.2
and §14; planned in [plan.md](plan.md) Milestone E5.

Decided with the owner on 2026-11-16:
- MCX keeps its own hours and holidays; index liveness counts NSE ticks only.
- The top bar follows the tab: on BULLION the market pill shows MCX status and the feed
  pill's age is the newest bullion tick; a closed market's quiet feed is muted, not red.
- Closed, holiday and pre-open banners are a prominent amber band with a bold title;
  errors stay red.

Builder's calls:
- The MCX close is a setting changed by hand with the US season (23:30 or 23:55), not
  worked out from daylight-saving rules.
- An MCX outage is logged (`bullion_gap_start` / `bullion_gap_end`); at the time it changed
  nothing else, and since E6 it also pauses bullion signals and trades.

### 10. Bullion signals and paper trades

Asked for (2026-11-16): create signals and paper trades for bullion (gold, silver), with
the bullion engines offset from the minute close so all engines do not run at once.

Status: built in Milestone E6; the bias, evidence and panels were checked on the live
feed. Design in [spec.md](spec.md) §6.6 and §9a, and [signal.md](signal.md) §13; planned in
[plan.md](plan.md) Milestone E6.

Decided with the owner on 2026-11-16:
- The near-month GOLD and SILVER futures (the full contracts already on the tab), long or
  short.
- Trend-only evidence (EMA cross, VWAP position, supertrend) on the bullion candles.
- The full MCX session: signals 09:15–22:45, square-off 23:00, all editable.
- Bullion ticks recorded to their own table, with a bullion replay.
- Journal: GOLD, SILVER and a bullion total; "overall" stays index options only.
- Bullion bias and signals run `eval_offset_seconds` (20) after each minute close.

Builder's calls:
- Minute-close entry only; no trigger, order-flow or shadow rule for bullion.
- Cost = fixed per lot + a % of round-trip turnover (CTT and charges scale with value).
- Bullion signals are not scored by the outcome yardstick (it measures NSE spot).

### 11. Live signal levels

Asked for (2026-11-16): the signal panel should update entry, target and stop while the
signal waits for the trader.

Status: built in Milestone E7, with unit tests. Design in [spec.md](spec.md) §9.3 and
§10.1, and [signal.md](signal.md) §7; planned in [plan.md](plan.md) Milestone E7.

Decided with the owner on 2026-11-16:
- Show both the fired levels and the live ones on the signal panel.
- A paper trade takes the live levels from its fill.
- On expiry day the points convert with the option's live delta.

Builder's calls:
- Percentage signals keep the ratios they fired with, so a config edit after firing does
  not move an open offer.
- Live levels go out once a second, with open-trade P&L.

### 12. Net volume per candle

Asked for (2026-11-16): does Upstox give data to show net volume for each one-minute
candle?

It does not: the feed and the candle API give total volume only. It can be derived from
the recorded ticks (volume change, last price, best bid and ask). On the last recorded day
the quote rule alone classified 85 % of NIFTY and 90 % of BANK NIFTY futures volume.

Status: built in Milestone E8. Design in [spec.md](spec.md) §7.1 and §13.2; planned in
[plan.md](plan.md) Milestone E8.

Decided with the owner on 2026-11-16:
- Prints between bid and ask are signed by the tick rule.
- A histogram under the price chart, from the near-month future (the metal's future on
  BULLION), with buy / sell / net in the legend.

Builder's calls:
- Display only; the order-flow score keeps its own seconds-scale signing.
- Minutes backfilled at start have no side data and show no bar; a replay rebuilds the
  split from the recorded ticks.

### 13. One Market view panel

Asked for (2026-11-16): combine the market view and evidence panels into one "Market
view" panel, and move the signal out of the market-view row so the view gets the full
width.

Status: built in Milestone E9 and checked in a browser. Design in [spec.md](spec.md) §13.1
and §13.2 "Panel order"; planned in [plan.md](plan.md) Milestone E9.

Decided with the owner on 2026-11-16:
- The signal panel sits above Market view by default.
- Inside Market view the meter is on top, full width, with the evidence below.

Builder's calls:
- A layout saved in the browser before this change is carried over: the old market
  view + signal pair becomes Signal then Market view in its place, and the old Evidence
  position is dropped.
- The merged panel keeps the old market-view panel's minimise state.

Also asked (2026-11-16): make the bullion panel's details collapsible like the index
panel's. Each metal card keeps its price and change on show; the rest sits behind a
Details toggle, closed by default, one remembered choice for both cards.

### 14. Headlines

Asked for (2026-11-16): does Upstox provide a news API for NIFTY, BANK NIFTY, gold and
silver; then, a headlines panel on the right (show, hide, collapse) with relevant news
from Upstox, latest first.

Upstox's News API (live since 17/04/2026) gives news per stock only: index, F&O and MCX
keys return nothing, so there is no gold or silver news. Over 11 heavyweight stocks it gave
about 25 items in 7 days, much of it market wraps.

Status: built in Milestone E10; the owner checks it in the browser. Design in
[spec.md](spec.md) §6.7, §13.1 and §13.2; planned in [plan.md](plan.md) Milestone E10.

Decided with the owner on 2026-11-16:
- The purpose is a quick check on what is moving the market, not an input to the signal.
- Headlines share the option chain's column, below the chain, rather than a column of
  their own.

Also asked (2026-11-17): how to tell today's news from the latest, and some colour.
Decided: headlines grouped by day under Today / Yesterday / date headers, earlier days
muted; the time in accent for the last hour; an accent bar for headlines not yet seen; and
stock chips coloured by index (BANK NIFTY violet, NIFTY only neutral). No green or red,
since they mean bullish and bearish in this app and Upstox gives no sentiment. Left out:
relative times ("12m ago"), a pre-open label, and a MARKET tag for market wraps.

Builder's calls:
- One market-wide list for every tab, from a hand-edited list of the 30 heaviest NIFTY and
  BANK NIFTY stocks (one Upstox call).
- Each story shown once, with chips for every stock it was attached to; summary on click;
  link opens the article in a new tab.
- The backend polls every 180 s while logged in and pushes changes; nothing is stored.
  Asked for (2026-11-17): the interval is a config parameter, `news.poll_seconds`
  (30–3600 s), edited and versioned in the app like the others; a save applies at once.
- Collapse is the panel's minimise; hide is a × on the panel and a Headlines toggle in the
  top bar.

### 15. Sector indices on the Index panel

Asked for (2026-11-17): add sector indices such as auto, FMCG and IT to the NIFTY 50
Index panel, and move ATM into the details section.

Status: built in Milestone E11; the owner checks it in the browser. Design in
[spec.md](spec.md) §7.4 and §13.2 (IndexTiles); planned in [plan.md](plan.md) Milestone E11.

Decided with the owner on 2026-11-17:
- NIFTY shows the main ten sectoral indices: Auto, FMCG, IT, Pharma, Metal, Energy,
  Realty, Media, Fin Service, PSU Bank.
- BANK NIFTY shows its bank sub-indices in the same place: PSU Bank, Pvt Bank, Fin Service.
- Each sector shows its name, level and change %.
- Then (2026-11-17): each sector in a small box like the NIFTY 50 figures, three lines:
  name, value, and change with change % in brackets.
- Then (2026-11-17): the sectors collapse like the details section, and the sector name
  is easy to read (it was small and muted).

Builder's calls:
- The lists are a setting (`sector_indices`), not a config parameter: they change the
  feed subscription, which is made at start.
- The Sectors block starts open and is remembered once closed; closed, it shows how many
  sectors are up and down. The change is green up and red
  down like the index's own change, and the value flashes on a tick like spot; boxes run
  five across on medium screens and up; hover shows the full name and previous close.
- ATM moves on both tabs, with the strike count, into a first Details group, Options.
- Sector ticks are recorded like VIX, so replays show them.

### 16. Dollar, crude and bullion in the signal

Asked for (2026-11-18): include the dollar index, crude prices and the gold and silver
trends in the signal calculation.

Status: built in Milestone E12; the owner checks it on the live feed. Design in
[spec.md](spec.md) §6.8 and §8.6, and [signal.md](signal.md) §3.4; planned in
[plan.md](plan.md) Milestone E12.

Decided with the owner on 2026-11-18:
- Live with a small weight from the start (10 % of the index bias).
- The dollar from the Upstox feed: Upstox has no dollar index, so it is rebuilt from the
  NSE currency futures, alongside USD/INR itself.
- Gold counts as risk-off (bearish for the indices); silver is shown but not scored.
- Bullion too: the gold and silver bias also weighs the dollar (10 %).

Builder's calls:
- The macro weight is carved out of the others in proportion, so no saved config needed
  changing; when no macro price is live (synthetic, the currency market after 17:00) the
  share goes back and the bias is what it was.
- Each reading is the move over 30 minutes; full strength at 0.15 % (dollar), 0.10 %
  (USD/INR), 0.80 % (crude), 0.40 % (gold). Starting values, not yet tuned.
- For bullion USD/INR counts as bullish: MCX prices are world prices times USD/INR.
- Macro ticks are recorded with MCX ticks (`bullion_ticks`), so they never stretch an NSE
  replay, and replay with `replay_bullion`.

### 17. More Upstox evidence in the bullion bias

Asked for (2026-11-18): what Upstox data, beyond what is used, would help the gold and
silver futures bias; then build the first part.

Status: built in Milestone E13; to be tuned once some weeks of MCX ticks are recorded.
Design in [spec.md](spec.md) §8.4 and §9a, and [signal.md](signal.md) §13.3, §13.4;
planned in [plan.md](plan.md) Milestone E13.

What Upstox has that the bias did not read (checked on the recorded `bullion_ticks`):
- Already on the socket and recorded: the futures' OI, total buy and sell quantity,
  five-level book quantity, the exchange's average price and the day candle.
- On Upstox but needing new subscriptions or calls: MCX options on GOLD and SILVER (an
  option chain: PCR, OI walls, implied volatility), daily candles with OI (multi-day
  levels, a volatility-sized target and stop), the mini contracts, the MCX bullion index,
  NSE gold and silver ETFs.
- Not on Upstox: the international gold price, US yields, the US data calendar, global
  ETF flows, commodity news (Upstox news is NSE stocks only).

Decided with the owner on 2026-11-18:
- First part: the futures' OI build-up, order flow and the other metal's trend.
- On with modest weights straight away: trend 0.60, OI 0.15, flow 0.15, other markets
  0.10, although 2.5 recorded sessions showed no clear edge for any of them.

Builder's calls:
- Order flow is two votes in a new `flow` group: net traded volume, and the book's lean
  against its own 30-minute average (silver's book leans to the sell side for hours, so
  the raw lean would hold it bearish).
- The other metal's trend goes in the macro group; its trend votes, not its bias, so
  neither metal reads itself.
- A group with no live reading gives its share to the others, so at start the bias is
  what it was until the new votes warm up.
- Recording gaps exposed two faults, both fixed: a volume jump after a feed gap was
  signed as one trade (now counted but unsigned, for the index net-volume bars too), and
  the OI change compared across a gap (now warming).
- Replay of 16–18/11/2026 (no costs; overlapping signals): 168 bullion signals before,
  80 after; SILVER +0.04 % → +0.10 % per signal, GOLD +0.04 % → −0.02 %. Too little data
  to judge either way.

### 18. GIFT Nifty in the signal

Asked for (2026-11-19): include GIFT Nifty as a factor in the signal calculation; does
the Upstox feed carry it in real time?

Status: built in Milestone E14. Design in [spec.md](spec.md) §6.8 and §8.6, and
[signal.md](signal.md) §3.4; planned in [plan.md](plan.md) Milestone E14.

What Upstox has (checked 2026-11-19):
- Not in the NSE or MCX instrument files. Its global instrument file lists
  `GLOBAL_INDEX|SGX NIFTY` (GIFT NIFTY, 06:30 Monday to 02:45 Saturday) with a 120 s
  refresh: not real time. Quote, LTP and 1-minute candles (today and past days) work;
  the WebSocket is not documented for it.
- No GIFT Bank Nifty.

Decided with the owner on 2026-11-19:
- Used for the opening gap only: during NSE hours it is a delayed copy of the NIFTY future
  the bias already reads. The overnight move is a NIFTY vote that fades over the first
  minutes, with a parameter to follow or fade the gap.

Builder's calls:
- The move is GIFT against itself (previous 15:29 to 09:14), so its premium over spot
  cancels; full strength at 0.50 %, fading over 30 minutes, follow by default. Starting
  values, not tuned.
- A member of the macro group, sharing its 10 % with the live readings, rather than a
  group of its own, so no saved config needed changing.
- REST only, fetched once a minute after the open (nothing reads it before 09:16), and
  stored per day so replays and `tools/score.py` see it. The global file is not
  downloaded: the key is fixed and a rename would show as a logged fetch failure.

### 19. Switch factors off in the Evidence panel

Asked for (2026-11-19): an on/off toggle in the Evidence panel to enable or disable a
factor in the bias; all factors on by default.

Status: built in Milestone E15. Design in [spec.md](spec.md) §8.4 and
[signal.md](signal.md) §4; planned in [plan.md](plan.md) Milestone E15.

Decided with the owner on 2026-11-19:
- Per index or metal: crude off on NIFTY leaves BANK NIFTY, GOLD and SILVER alone.
- A quick switch, not a config version: a click makes no new version.

Builder's calls:
- What was off is still on record: every stored bias minute and signal marks each factor
  `enabled`.
- A factor switched off stays visible with its reading; its group's other live factors
  share its weight, and a group with every factor off hands its share to the others.
- A switch applies from the next minute close, never mid-minute, so a click cannot fire a
  signal between closes.
- Switches are kept in the database (`app_state`), so they survive a restart; replays use
  that database's switches, `tools/score.py` none.
- `info` rows (silver, a faded GIFT vote) get a switch too; it changes nothing.

## Deferred

### Chart zoom buttons

Zoom-in and zoom-out buttons on the charts. Left for now (decided 2026-11-13).

Notes:
- The chart is `frontend/src/components/PriceChart/PriceChart.tsx` (lightweight-charts).
- A "reset" or "fit the day" button alongside is worth considering when this is picked up.
