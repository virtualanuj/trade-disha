# TradeDisha — Enhancements

The companion to [intent.md](intent.md): every improvement asked for after release
1.0.0, as it was asked, with what was decided, by whom and when, and where it was built.
The design is in [spec.md](spec.md) and the milestones in [plan.md](plan.md).

From time to time the owner compacts by hand: the enhancements are merged into intent.md
as if they had always been requirements. Until an item is merged, intent.md and this file
together are the requirements. Wording below such as "since", "now" or "superseded" is as
of the request.

**Merged into intent.md:** items 1 to 32 (items 1 to 22 compacted 25/11/2026, 23 to 32 on
27/11/2026). Items added after 32 are not merged yet.

## UI

### 1. Resizable panels

Make the panels resizable.

Status: built in Milestone E1 and checked in a browser. Requirement in
[intent.md](intent.md) ("The screen"); design in [spec.md](spec.md) §13.2 "Resizable
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

Status: Milestones S1 (recording and scoring) and S2 (order-flow trigger in shadow) built;
the order-flow fields are recorded live and the shadow rule has run on the live sessions of
16–18/11/2026. S3 (switch on, on evidence) waits for at least five live sessions of shadow
data. Requirement in [intent.md](intent.md); design in [spec.md](spec.md) §6.2,
§8.5, §9.5, §9.6, §11, §12; milestones S1 to S3 in [plan.md](plan.md).

Not included: targets and stops sized from theta, gamma and vega; choosing a strike other
than ATM (analysed, not built: see the strike ladder under Deferred); the 30-level order
book.

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

### 8a. Config drawer

Asked for (2026-11-19): make the config dropdown a right-side panel; each parameter's and
factor's explanation shown clearly in the line below its name; tabs for the parameters,
the factors and the version history; clear ways to close it.

Status: built and checked by the owner in the app (commit a891615). Design in
[spec.md](spec.md) §13.2 (Config control); noted in [plan.md](plan.md) under "Config
drawer".

Decided with the owner on 2026-11-19:
- A drawer on the right over a dimmed backdrop, with tabs **Parameters**, **Factors** and
  **Versions**, opening on Parameters.
- The explanation sits on the line below each name, not behind an (i) button (tried first
  and dropped the same day); the limits go on a line of their own ("Allowed: …").
- Each factor gets a one-line plain explanation, beside its toggle.
- It closes from a clear ✕ Close button, its header line, the backdrop or Escape.

Builder's calls:
- Unsaved parameter edits are kept when a new version arrives (a factor flip, for
  instance); values not touched follow the new version.
- The factor explanations are written in `frontend/src/lib/factors.ts` (`FACTOR_HELP`),
  from [signal.md](signal.md) §3, since the backend's switch descriptions are only names.

### 8b. Chain parameters that are not read (open)

Found in the docs review of 2026-11-19: `chain.strike_window` and
`chain.recenter_strikes` are parameters, so they show in the Parameters tab and can be
saved, but no code reads them. The option chain takes its width and re-centring from the
process settings `TRADEDISHA_STRIKE_WINDOW` and `TRADEDISHA_RECENTER_STRIKES` (defaults 10
and 2, restart needed). Editing them in the app does nothing.

To decide: wire the chain to the parameters (re-centring could take a new value at the
next minute close; the window width changes the subscriptions), or remove them from the
parameter model and `config/params.toml` so the editor stops offering them.

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
  *(Since items 16 and 17: also the dollar, the future's OI, order flow and the other
  metal.)*
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

Changed the same day (Milestone E16), decided with the owner:
- The switches move into the versioned config. They are flipped only in the Config control
  (since 8a, the Factors tab of the Config drawer),
  and each flip creates a version automatically with a fixed tag naming the change
  (`Factor NIFTY.pcr: off`).
- The Evidence panel shows each factor's switch state clearly, read only.
- Every factor starts on: switches set under E15 are not carried over.

Builder's calls (E16):
- A Factors tab in the Config control rather than a section of the Edit form: each flip is
  a new version, and the form started again on a new version, which would drop half-typed
  edits. *(Since 8a the form keeps unsaved edits across a new version; the tab stays.)*
- The typed editor does not list the switches, and a typed save keeps them as they are.
- A test keeps the switch names equal to the factors the engines produce, so a new factor
  cannot ship without a switch.

### 20. A paper bank account that funds paper trades

Asked for (2026-11-20): a fake bank account that funds trades. On each paper trade, check
the bank has the money and block it; on close, deduct the loss or deposit the profit. The
initial money is configurable in the Config menu.

Status: built in Milestone E17. Design in [spec.md](spec.md) §10.5; planned in
[plan.md](plan.md) Milestone E17.

Decided with the owner on 2026-11-20:
- A future blocks a margin % per metal (GOLD 10 %, SILVER 12 %, both parameters). An option
  blocks its premium. Both add the round-trip cost.
- One account for index options and bullion, and no data is ever deleted.
- Changing the opening balance is cash moving: a bigger amount deposits the difference,
  a smaller one withdraws it. P&L made so far keeps counting. (First built as a fresh
  account on each change; changed the same day.)
- The default opening balance is ₹25 lakh.

Builder's calls:
- The balance is worked out from the trades each time, not stored, so it cannot drift.
- A refused trade leaves the signal active, so it can be taken once money frees up.
- A futures loss can exceed its margin, so the balance can go negative; no new trade opens
  until money is deposited.
- A withdrawal is not capped by the free money (a Config save is not refused over the
  bank); available can go below zero, and new trades are refused until trades close.
- Saving the same opening balance again moves no cash. The journal lists every cash move.

### 21. Pause bullion signals around US data releases

Asked for (2026-11-23): what could be added to the bullion signal beyond the Upstox data
it already reads; then the owner chose a pause around US data releases as the first part.

Status: built in Milestone E18. Design in [spec.md](spec.md) §9a and [signal.md](signal.md)
§13.6; planned in [plan.md](plan.md) Milestone E18.

Decided with the owner on 2026-11-23:
- US data releases come from a hand-kept file, `config/us-events.txt`, no API.
- What the pause stops is configurable: new signals always; ending a waiting signal and
  refusing a manual paper trade are each a switch in Config.

Builder's calls:
- 15 minutes before and after each release by default; both 0 turns the pause off.
  Both extra switches are off by default.
- Times in the file are IST, converted by hand (08:30 New York is 19:00 IST in US
  standard time, 18:00 in daylight time), as MCX's close is changed by hand. FOMC
  decisions fall after the 22:45 end of bullion signal hours, so they need no line.
- The file is read at start, like the holiday files; a bad file is logged and bullion runs
  without a pause rather than not starting.
- A waiting signal ended by the pause is `lapsed`, not a new status.
- The bias is still worked out and stored during the pause; only firing stops. Open
  trades are never touched.

What else could be added to the bullion signal (listed on 2026-11-23, not built):
- Already on hand: MCX crude (subscribed for the index bias, unused by bullion), the
  gold/silver ratio trend, the calendar spread, day levels (opening range, previous close).
- On Upstox, needing new calls: MCX options on GOLD and SILVER (PCR, OI walls, implied
  volatility); daily candles with OI (previous-day high and low, pivots, an ATR-sized
  target and stop); the mini contracts; the MCX bullion index; NSE gold and silver ETFs.
- From data already recorded: a volatility regime; a 5- and 15-minute trend.
- Not on Upstox: international gold and silver (spot, COMEX), likely the strongest single
  input; US real yields, the actual dollar index, S&P futures, VIX; slow data (ETF
  holdings, CFTC positioning).

### 22. A page of executed paper trades

Asked for (2026-11-25): a view for executed paper trades.

Status: built in Milestone E19. Design in [spec.md](spec.md) §13.2 ("Trades page");
planned in [plan.md](plan.md) Milestone E19.

Decided with the owner on 2026-11-25:
- A separate page, not a dashboard panel or a change to the Journal: the TopBar has
  Dashboard · Journal · Trades, and the page is `#trades`.
- Each trade opens to its detail: levels, fills, P&L, the signal it was taken on and the
  evidence at that minute.

Builder's calls:
- Closed trades only; open trades stay on the dashboard, where they have live P&L and the
  Close button. Index options and bullion together, filtered by market and dates.
- Grouped by IST entry day, newest first, each day with its trade count, won/lost
  (net-positive) and net.
- The detail is fetched when a trade is first opened (`GET /api/paper-trades/{id}`) and
  kept while the page is open. It shows risk : reward from the fill and the result in R
  (net over the money between fill and stop), and what the signal's instrument did next
  (the outcome the scorecard uses).
- The evidence is the breakdown stored with the signal, shown in the same table as the
  dashboard's Market view panel; a factor switched off then reads "off".
- This is the "click-through to the originating signal's breakdown" the Journal page
  promised in the first spec and never had.

Follow-up from the owner (2026-11-25): remove from the Journal what the Trades page already
shows. The Journal's trade table is gone; it keeps the bank, the ledger and the summary
cards, and links to the Trades page. The table's Exit and Fill filters moved to the Trades
page.

Follow-up from the owner (2026-11-25): include open trades in the Trades page. They head
the page under "Open now" with their unrealised total, at the live price from the socket;
the Exit and Fill filters, which only a closed trade can match, hide them.

Follow-up from the owner (2026-11-25): an open trade can be closed from the Trades page.
Each open row has the dashboard's Close button: one click closes at the current price
(no confirm step, as on the dashboard), disabled while that trade's market has no live
price, and a refusal is shown with the server's reason.

### 23. Paper trades opened by hand

Asked for (2026-11-26): open a paper trade at will, without a signal.

Status: built in Milestone E20. Design in [spec.md](spec.md) §10.1 ("Opened by hand",
"Changing the levels"), §10.3, §12.1 and §13.2 (TradeTicket, LevelsEditor); planned in
[plan.md](plan.md) Milestone E20.

Decided with the owner on 2026-11-26:
- From the option chain (each call and put price opens a ticket for that strike, any
  strike in the window) and, on the BULLION tab, Buy and Sell on each metal's card.
- Target and stop are the signal rule's at the price, and the trader can change them on
  the ticket before opening.
- The target and stop of any open trade, from a signal or by hand, can be changed later,
  from Open paper trades and from the Trades page. Every change is recorded.
- In the Journal these trades have their own "Opened by hand" card and are kept out of
  overall, per index, bullion and per metal, so those still measure the signals. The bank
  counts them like any other trade.
- The same gates as a signal trade (market open, feed live, before the square-off, the bank
  can fund it, the US-release pause for bullion when it refuses trades), plus the signal
  cut-off: no index trade from 15:00 (13:00 on expiry day), no bullion trade from 22:45.
- One constant, `manual`, is the `signal_id` of every trade opened by hand (the owner's
  call, over a nullable column).

Builder's calls:
- Levels left as they are on the ticket are worked out again at the fill, as a signal
  trade's are; typed ones are kept. Either way they must stand at the fill (target above
  and stop below, mirrored for a short), or the open is refused with the reason. The same
  check runs on a change of levels, against the price then, so a change needs a live feed.
- `signal_entry` keeps the price the ticket showed and `slippage` is the fill minus it, so
  a hand trade records its ticket-to-click slippage as a signal trade does.
- Signal trades stay one click from the signal card; their levels can be changed once open.
- Signal trades are still not held to the cut-off: a signal fired at 14:59 can be traded
  until it lapses, as before.
- Each bullion card has its own Buy and Sell, rather than buttons for the focused metal
  only.

### 24. Target and stop in whole rupees

Asked for (2026-11-26): target and stop numbers should be rounded off to the nearest value.

Status: built in Milestone E20 (a follow-up to item 23). Design in [spec.md](spec.md) §9.3
("Whole rupees").

Decided with the owner on 2026-11-26:
- The nearest whole rupee, for every instrument (not the exchange tick).
- Everywhere: signal levels as fired and live, a paper trade's levels at its fill (from a
  signal or by hand), the ticket's levels, and levels the trader types or changes.

Builder's calls:
- Half a rupee rounds up.
- A level the rounding would put on or past the entry (a cheap option: entry 2.00, stop
  1.70 rounds to 2) moves out to the next whole rupee beyond it, so a trade never opens on
  its own target or stop. An option's stop keeps its 0.05 floor, so below a rupee the stop
  is 0.05.
- A typed level is only rounded, never moved: one that rounds onto or past the price is
  refused with the reason.
- A percentage signal's live levels keep the ratios of its rounded fired levels, so they
  can differ from the configured percentages by up to half a rupee over the entry (under
  1 % for premiums above ₹50).
- The ticket's and the editor's boxes step by a rupee; a decimal can still be typed and is
  rounded by the server.

### 25. Gold BeES and Silver BeES on the BULLION tab

Asked for (2026-11-26): add Silver BeES and Gold BeES to the BULLION tab.

Status: built in Milestone E21. Design in [spec.md](spec.md) §6.6 ("Gold and silver
ETFs") and §13.2 (BullionCards); planned in [plan.md](plan.md) Milestone E21.

Decided with the owner on 2026-11-26:
- To watch them alongside the MCX futures: display only, no signals or paper trades.
- Each ETF's own quote only: price, change, the day's range, previous close, ATP, volume,
  bid and ask, and the 52-week range. No comparison with the MCX price (Upstox sends no
  iNAV, so any premium would be an estimate).

Builder's calls:
- Nippon's GOLDBEES and SILVERBEES, by their `NSE_EQ` keys in the Upstox NSE file, listed
  in a setting (`bullion_etfs`), not a config parameter: they change the subscription,
  which is made at start.
- Each ETF's card sits under its metal's card and opens with the same Details toggle.
  *(Superseded by item 31: each card opens on its own; and by item 32: the ETFs have
  their own tab, NSE's BULLION.)*
- They are NSE instruments: NSE hours, counted as NSE ticks and recorded in `ticks` like
  the sector indices, so a replay of a later day shows them. While NSE is not trading the
  card keeps the last price with a muted "NSE closed" (or holiday, pre-open) note, since MCX
  trades on.
- They show only where the tab does (while the MCX futures are loaded); synthetic has none.
- The start quote and 52-week range are fetched on the live feed only; a replay shows
  them from the recorded ticks.

### 26. A rates strip under the top bar

Asked for (2026-11-26): a strip below the top menu bar with the current rates of NIFTY,
SENSEX, gold, silver, Gold BeES and Silver BeES.

Status: built in Milestone E22. Design in [spec.md](spec.md) §7.4 ("SENSEX"), §12 and §13.2
(RatesStrip); planned in [plan.md](plan.md) Milestone E22.

Decided with the owner on 2026-11-26:
- Each entry shows the price and the day change %.
- On every page. A click opens the entry's tab on the dashboard: NIFTY its tab, a metal or
  an ETF BULLION with that metal in focus; SENSEX is not clickable (it has no tab).

Builder's calls:
- SENSEX is new to the app: `BSE_INDEX|SENSEX` subscribed with India VIX and the sector
  indices, recorded in `ticks` and counted toward liveness like them, and sent in a new
  small `quotes` list (`GET /api/quotes`, `hello`, a `quotes` frame).
- NIFTY is the live spot, so the strip moves with the Index tile; its change % is against
  the stats' previous close.
- "Gold" and "silver" are the MCX near-month futures already on BULLION.
- All six always show, in a fixed order; a rate not known yet is "—" (synthetic has only
  NIFTY). Prices are formatted as on the cards; the change is coloured by its sign, so a
  small move still shows its side.
- A narrow window scrolls the strip sideways rather than wrapping it.

### 27. Hover previews on Trades, Data and Latency

Asked for (2026-11-26): hovering on Trades shows the open trades, on Data the data, and
on Latency the latency numbers.

Status: built in Milestone E23. Design in [spec.md](spec.md) §13.2 (TopBar, "Hover
cards"); planned in [plan.md](plan.md) Milestone E23.

Decided with the owner on 2026-11-26 (on the builder's proposal):
- Clicks are unchanged; hovering adds a read-only card under the button.
- Trades: every open paper trade, all markets, one line each with entry, now and live net
  P&L, and the total. Data: the stored-data figures (database size, ticks, days, oldest and
  newest day); deleting stays behind the click. Latency: p95 per hop against its budget,
  over budget in red, and the live receive and paint times.
- The card opens after about a quarter of a second (so passing over the bar opens
  nothing), also on keyboard focus, and closes on leaving or Esc; none while the full view
  is already showing.

Builder's calls:
- A click closes the card (the click does the button's own thing).
- The buttons' native tooltips are dropped, since they would cover the card; each card
  ends with a line on what the click does.
- The Latency card refreshes every 2 s while open, like the overlay; the Data card fetches
  once as it opens.

### 28. GOLDM and SILVERM, and lots per contract

Asked for (2026-11-27): enable GOLD, GOLDM, SILVER and SILVERM for bullion, and make the
default trading size configurable for each commodity.

Status: built in Milestone E24. Design in [spec.md](spec.md) §6.6 ("Minis"), §9a ("The
contract traded"), §10.1 and §13.2 (BullionCards, TradeTicket, SignalCard); planned in
[plan.md](plan.md) Milestone E24.

Decided with the owner on 2026-11-27:
- The minis are a trading choice per metal, not instruments of their own: the bias and
  signals stay on GOLD and SILVER; Config picks what each metal's signal trade opens
  (GOLD or GOLDM, SILVER or SILVERM), with default lots for each of the four contracts.
- Each mini has a card under its metal with Buy and Sell for a trade by hand.
- The ticket has a Lots box filled with the contract's default, which can be changed for
  that trade; one-click signal trades always use the default.

Builder's calls:
- `bullion.lots` becomes `gold_lots`, `goldm_lots`, `silver_lots` and `silverm_lots`; a
  version saved before has its `lots` read as all four, so it still loads.
- A mini trade is its metal's: GOLD's margin %, GOLD's journal row, the US-release pause.
  Its levels are worked out at the mini's fill; slippage is the mini's fill against the
  signal's GOLD entry.
- A configured mini that is not loaded refuses the signal trade with the reason, rather
  than trading the full contract (ten times the size).
- The signal card says what its trade opens ("trades GOLDM ×3"); trades name a mini
  ("GOLDM FUT long").
- Index option tickets have no Lots box (the request was for commodities); the API takes
  `lots` for any trade.
- The minis are not on the rates strip.

### 29. The BULLION tiles follow the metal switch

Asked for (2026-11-27): on BULLION, GOLD shows only the gold cards and SILVER only the
silver ones.

Status: built as a follow-up in Milestone E24. Design in [spec.md](spec.md) §13.2
(BullionCards).

Decided with the owner on 2026-11-27:
- The GOLD / SILVER switch, which already picks the metal for every other panel, also
  picks the cards: GOLD shows GOLD, GOLDM and GOLDBEES; SILVER shows SILVER, SILVERM and
  SILVERBEES. *(Superseded by item 32: GOLD and SILVER are MCX tabs, and the ETFs are on
  NSE's BULLION tab.)*

Builder's calls:
- The metal's card runs across the panel, with the mini's and the ETF's cards side by side
  under it (each stacks on a narrow window).
- The gold/silver ratio stays under the cards, since it needs both metals.
- The panel's minimised summary still lists both metals' prices and the ratio.

### 30. Details on the GOLDM and SILVERM cards

Asked for (2026-11-27): GOLDM and SILVERM get details like GOLD and SILVER.

Status: built as a follow-up in Milestone E24. Design in [spec.md](spec.md) §6.6
("Minis") and §13.2 (BullionCards).

Decided with the owner on 2026-11-27:
- The mini cards get the same Details as the metal cards: the day's range, ATP,
  liquidity (volume, OI, bid and ask, spread, buy and sell quantity), the contract's year
  and circuit limits, and the next month with the calendar spread.

Builder's calls:
- Each mini is loaded as a contract of its own, with its next month, start quote and
  one-year range (two more requests at start), so its card is the metal's card.
- One Details toggle still opens every card. *(Superseded by item 31.)*
- Every card's heading gives the rupees per point a lot (the mini card had it; the metal
  cards now do too).

### 31. Details open only the card clicked

Asked for (2026-11-27): Details should open and close only the card clicked, not all of
them on the page.

Status: built as a follow-up in Milestone E24. Design in [spec.md](spec.md) §13.2
(BullionCards).

Decided with the owner on 2026-11-27:
- Each bullion card's Details (GOLD, GOLDM, GOLDBEES, SILVER, SILVERM, SILVERBEES) opens
  and closes on its own.

Builder's calls:
- Each card's choice is remembered on its own (`tradedisha.bullionDetailsOpen.<card>`), so
  a reload keeps it; every card starts closed, and the old shared key is no longer read.

### 32. Tabs by exchange: NSE and MCX

Asked for (2026-11-27): NIFTY and BANK NIFTY are tabs in NSE, with a third NSE tab,
BULLION, showing SILVERBEES and GOLDBEES.

Status: built in Milestone E25. Design in [spec.md](spec.md) §13.1 and §13.2 (IndexTabs,
MCX tabs, NSE BULLION tab, RatesStrip); planned in [plan.md](plan.md) Milestone E25.

Decided with the owner on 2026-11-27:
- The tabs are grouped by exchange: NSE — NIFTY, BANKNIFTY, BULLION (the two ETFs); MCX —
  GOLD and SILVER.
- NSE's BULLION shows only GOLDBEES and SILVERBEES. Each MCX tab is what the BULLION tab
  was for that metal: the future, its mini, signal, market view, chart, open trades and
  signals today. The GOLD / SILVER switch goes; the tab picks the metal.

Builder's calls:
- Each group shows while it has data; a group with no tabs is left out.
- NSE's BULLION has no signal, market view, chart or trades to show, so its main column is
  the ETF panel alone and there is no option chain; the top bar and banner follow NSE.
- On an MCX tab the metal's card and its mini's sit side by side, with the gold/silver
  ratio under them.
- The rates strip opens GOLD and SILVER on their MCX tab and the ETFs on NSE's BULLION.
- The panel layout is shared by every tab, as before; the remembered metal choice
  (`tradedisha.bullionChart`) is no longer used.

### 33. The Journal as the bank statement; the summary on Trades

Asked for (2026-11-27): move the paper-trade journal cards to the Trades page, below the
executed trades. Fill the Journal page with a detailed view of the bank transactions.

Status: built in Milestone E26. Design in [spec.md](spec.md) §10.5 (Statement) and §13
(Journal page, Trades page); planned in [plan.md](plan.md) Milestone E26.

Decided with the owner on 2026-11-27:
- The Journal is a full statement: every cash move, oldest first. That is the opening
  deposit, deposits and withdrawals, and for each funded trade a "Blocked" row when it
  opened and a "Settled" row when it closed (block released, net P&L settled), each with
  the running balance, blocked and available. Filters: date range, kind, market.
- The summary cards follow the Trades page's Market, From and To filters; Exit and Fill
  narrow only the table.

Builder's calls:
- Nothing new is stored: the statement is worked out from `bank_ledger` and the funded
  `paper_trades`, as the bank's figures already are.
- The running figures are over the whole history, so a filtered row shows the bank as it
  stood. Cash moves belong to no market, so a market filter shows trade rows only.
- The opening deposit is always the first row: ledger rows carry the wall clock and
  trades the market clock (another day in a replay).
- The bank strip stays at the top of the Journal; the ledger table under it goes, since the
  statement holds its rows. A trade on the statement links to the Trades page.

### 34. Trades: a table that folds away, and side tags in place of colour

Asked for (2026-11-27): on the Trades page, make the paper-trade table collapsible
(show/hide). Do not colour the trade name (first column) green or red; tag it short, long,
call or put instead.

Status: built in Milestone E26. Design in [spec.md](spec.md) §13 (Trades page); planned
in [plan.md](plan.md) Milestone E26.

Builder's calls:
- The toggle sits at the top of the table's box and shows the count ("Hide the trades
  (3)"). Folding hides only the table; the filters and summary cards stay. The choice is
  remembered in this browser, and the table starts open.
- One neutral tag style for all four words, so the word carries the side. An option reads
  "NIFTY 25000 CE call"; a future "GOLD FUT short" (a mini, "GOLD GOLDM FUT long").
- Only the Trades page's first column changes; the dashboard's open-trades panel and the
  signal detail keep their colours.

### 35. A better summary on the Trades page

Asked for (2026-11-27): improve the summary on the Trades page, make it go with the
trades table, and include more useful information.

Status: built in Milestone E26 (it supersedes the summary cards of item 33). Design in
[spec.md](spec.md) §13 (Trades page); planned in [plan.md](plan.md) Milestone E26.

Builder's calls:
- "Goes with the table": the summary heads the table's own box and is worked out on the
  page from the rows the table shows, so every filter moves it, exit reason and fill
  included (item 33 had it follow only market and dates). It stays when the table is
  folded.
- Added: profit factor, per trade (expectancy) and average R, best and worst trade, max
  drawdown, the longest run of losses, costs, and open trades' live net, counted apart.
  Kept: net and gross, hit rate, average win and loss, exits by reason, average time held,
  and exits not on a live price.
- A compact "by market" table replaces the cards, with the same groups as before (Index
  options, Bullion, Opened by hand). A group is split into markets only when it has two or
  more, and the table shows only when the rows span more than one group or market.
- `/journal/stats` stays on the server, but the page no longer calls it.

### 36. Chart intervals: 10 s, 30 s, 1 m, 5 m

Asked for (2026-11-27): an option to see the charts at 10 seconds, 30 seconds, 1 minute
and 5 minutes, instead of the fixed 1-minute interval.

Status: built in Milestone E27. Design in [spec.md](spec.md) §7.1 (Chart intervals) and
§13 (PriceChart); planned in [plan.md](plan.md) Milestone E27.

Decided with the owner on 2026-11-27:
- The lines (EMA fast and slow, VWAP, supertrend) and the net-volume pane are recomputed
  on the chosen interval's bars, with the same functions and parameters.
- Index (NIFTY, BANK NIFTY) and MCX (GOLD, SILVER) charts both get the switch.

Builder's calls:
- Display only: the market view, signals and paper trades stay on 1-minute closes. Signal
  markers sit on the bar that holds their minute.
- Periods count bars, so a 9-bar EMA is 90 seconds at 10 s and 45 minutes at 5 m.
- 10 s and 30 s bars are built from ticks and survive a restart (today's stored ticks are
  replayed at start, except in replay). 5 m bars group the 1-minute candles, so they
  include backfilled minutes. Only closed bars are drawn, as before.
- One choice for every tab, remembered in the browser; 1 m is the default.

### 37. Open trades stand out on the Trades page

Asked for (2026-11-27): on the Trades page, highlight the active trades in the trade table
so they are easy to notice.

Status: built in Milestone E28. Design in [spec.md](spec.md) §13 (Trades page); planned
in [plan.md](plan.md) Milestone E28.

Builder's calls:
- An open trade's rows, including its levels editor and detail when opened, are tinted
  in the accent colour with an accent bar down the left edge. It is not green or red, which
  mean profit and loss there.
- A pulsing dot before the trade's name and on the "Open now" row says it is live. Under
  reduced motion the dot stays still.
- Open trades still come first under "Open now", as before.

## Deferred

### Strike ladder (ATM ±3)

Signals that recommend, and score, options from three strikes in the money to three out
of the money instead of the ATM strike alone. Analysed on 2026-11-17 in
[strike_ladder_analysis.md](strike_ladder_analysis.md) (complexity, performance and data
needs); nothing is built.

### Chart zoom buttons

Zoom-in and zoom-out buttons on the charts. Left for now (decided 2026-11-13).

Notes:
- The chart is `frontend/src/components/PriceChart/PriceChart.tsx` (lightweight-charts).
- A "reset" or "fit the day" button alongside is worth considering when this is picked up.
