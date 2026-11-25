# TradeDisha — Intent and Requirements

## Purpose

TradeDisha is a personal trading assistant for NSE index options (NIFTY and BANK NIFTY)
and for MCX gold and silver futures. While each market is open it watches it
continuously, forms a view on whether it is turning bullish or bearish, and when that view
is strong enough it recommends a specific trade: an option to buy on an index, or a future
to buy or sell on a metal. Every recommendation comes with the reasons behind it, so the
trader can judge it rather than follow it blindly.

The trader places real orders themselves in their broker's app. TradeDisha never places a
real order. It offers paper trading instead, funded by a paper bank account, so the trader
can test the recommendations with virtual money and build a track record of how well they
work.

## Who it is for

A single trader, running the application on their own computer, looking at it in a web
browser through the trading day and the MCX evening session. There are no other users, no
accounts to manage, and no hosting.

## What success looks like

- The trader opens the app in the morning and, within a minute, sees the live state of the
  market and a live option chain without needing to look anywhere else.
- When the app recommends a trade, the trader can see in one glance what the recommendation
  is, why it was made, and what entry, target, and stop it suggests.
- The trader can paper-trade a recommendation with one click, watch it live, close it when
  they choose, and later open it again to see why it was taken and how it played out,
  alongside every other paper trade, with hit rate, profit or loss and the bank balance.
- Over weeks of use, the journal and the scores kept for every recommendation give an
  honest answer to the question "are these signals worth real money?"

## What would make it a failure

- A recommendation whose reasons are hidden or vague.
- Market data that is stale, delayed, scraped, or otherwise not trustworthy, shown as if it
  were live.
- Paper trades that open on their own. A paper trade must only ever start because the
  trader clicked.
- Any path by which the application places a real order.

## Qualities the application must have

These apply to the whole product, not to one feature.

1. **Modern, fast user interface.** A dense, high-contrast trading-terminal look, dark by
   default with a light option. Prices, the option chain, the meter and the chart update
   smoothly and continuously; the page never freezes, flickers, or needs a refresh, and a
   number changing on screen never makes the things beside it jump.
2. **Low latency.** A change in the market should be visible on screen within a quarter of
   a second of it reaching the application, and a new recommendation should appear within
   a tenth of a second of the app seeing the minute close. The delay between the broker and
   the application is outside the app's control, but it is measured and shown so the trader
   always knows how fresh the data is. The app must stay this responsive for a full trading
   day without slowing down, including after hours in a browser tab left in the background.
3. **Clean, maintainable code.** The code is written so that a competent developer who has
   never seen it can read it, change it, and trust it: small well-named parts, automated
   tests for all the trading logic, consistent style enforced by tools, and no hidden
   behaviour.
4. **Tunable signal algorithm.** Everything that shapes a recommendation — the weight of
   each kind of evidence, the thresholds, the indicator settings, targets and stops,
   time cut-offs — can be changed by the trader in the app, without restarting; the new
   values take effect from the next minute. Each individual piece of evidence can also be
   switched off for one index or metal. Every saved set is kept as a numbered version that
   can be brought back (see "Configuration" under "The screen").

## Scope

### Markets covered
- NIFTY 50 index options.
- BANK NIFTY index options.
- The nearest expiry for each (weekly for NIFTY; monthly for BANK NIFTY, which no longer
  has weekly expiries), covering the strikes around the current market price.
- On expiry day the app keeps working the expiring contract for the whole session, since
  that is often the most active trading day. It switches to the next expiry only after the
  market closes.
- Expiry day has its own rules, because premiums decay fast and open-interest readings are
  distorted by positions being closed out:
  - targets and stops are set in index points, not as a percentage of the premium;
  - no new recommendations after 13:00;
  - the evidence breakdown makes clear that it is expiry day and that open-interest
    readings should be trusted less.
- Gold and silver as traded in India: the near-month MCX futures of GOLD (₹ per 10 g) and
  SILVER (₹ per kg), the full contracts rather than the minis. The broker has no spot
  price for them, and these are what Indian markets quote. A metal moves to the next
  month's contract on its expiry day.

### Data
- Live prices, open interest and the order book (the quantities waiting to buy and to
  sell, and what has traded) from a reliable, official broker data feed that is free to
  use with a broker account.
- No scraping of websites, no unofficial feeds, no delayed data presented as live.
- Other markets read from the same broker, for the market view: the dollar (rebuilt from
  the NSE currency futures, since the broker has no dollar index), the rupee against the
  dollar, crude oil, gold and silver. GIFT Nifty is available from the broker only with a
  two-minute delay, so it is used for the overnight gap at the open, not during the
  session.
- The latest headlines from the broker. The broker carries news for individual NSE stocks
  only, not for indices, gold or silver, so the headlines are those of the heaviest NIFTY
  and BANK NIFTY stocks.
- Market data, the app's own calculations, recommendations, paper trades and the paper
  bank's history are all kept on the trader's computer so past days can be reviewed, and
  replayed, later. Gold and silver are recorded apart from the index market, so the
  evening session never stretches a replay of the NSE day.
- Raw tick data is the bulky part. The trader can delete raw ticks up to and including a
  chosen date from within the app, and the space goes back to the disk. Everything derived
  from them (minute candles, option-chain history, market views, recommendations, paper
  trades) is always kept.

### Market view (bias)
- For each index and each metal, the app maintains a continuously updated view: bullish,
  neutral, or bearish, with a strength.
- The view is refreshed every minute while the market is open.
- An index's view is built from these kinds of evidence:
  1. **Price trend** — the direction and momentum of the index itself.
  2. **Open interest** — where positions are building up in the option chain, the balance
     between puts and calls, and how that is shifting. A build-up is read by which way the
     premium moved: new open interest on a call whose premium rose is buying, not writing.
  3. **Premium behaviour** — whether call and put premiums, and their implied volatility,
     agree with the move in the index.
  4. **Other markets**, with a small weight — the dollar, the rupee, crude oil and gold;
     for NIFTY also GIFT Nifty's overnight move, which counts at the open and fades out
     over the first half hour.
- A metal's view is built from its own price trend, the build-up of open interest in its
  future, its order flow (buying against selling volume, and which way the order book
  leans), and, with a small weight, the dollar, the rupee and the other metal's trend.
- Each kind of evidence contributes a vote and a weight. The trader can see every vote.
  A reading that is not live (a market that is closed, a price that has gone stale)
  carries no weight, and its share goes to the evidence that is live.
- Any single piece of evidence can be switched off for one index or metal. It is still
  shown, but carries no weight, from the next minute.
- The model must be able to take on further kinds of evidence later, in particular news
  flow and FII/DII buying and selling.

### Recommendations (signals)
- When the view for an index becomes strong enough, the app issues a recommendation: buy a
  specific call option (bullish) or a specific put option (bearish), at the strike closest
  to the current index level. On the indices the app recommends buying options only: no
  selling, no spreads, no multi-leg strategies.
- When the view for a metal becomes strong enough, the app recommends buying its future
  (bullish) or selling it (bearish). This is the one place the app recommends selling.
  Gold and silver play no part in the index views or recommendations.
- A recommendation states: the market, the exact contract (for an option its strike,
  expiry and side), a suggested entry price, a target, a stop, the time it was issued, the
  configuration version it was made under, and a breakdown of the evidence that produced
  it.
- Only one recommendation per index or metal is active at a time.
- While a recommendation waits, it shows both the entry, target and stop it was issued
  with and the same levels worked out from the price now, updated every second.
- A recommendation lapses if it is not acted on within a short window, or if the market
  view reverses or weakens back to neutral.
- If the view is still strong enough when a recommendation ends (taken or lapsed), a fresh
  recommendation is issued at the current price. The trader is never left without a
  current recommendation while the view supports one.
- Open paper trades never block recommendations, in either direction. Whenever a
  recommendation is issued while paper trades are open on that market, it prominently
  shows the key facts of each open trade (which contract, entry price, current profit or
  loss, time held) so the trader can decide whether to close one first.
- An open paper trade is flagged "view reversed" whenever the current view opposes it, and
  the flag clears if the view comes back.
- No new recommendations are issued in the final part of each market's day, so that
  trades are not opened with too little time left.
- Recommendations must come early and seldom be wrong. To know, the app keeps score: every
  index recommendation, taken or not, is followed to see whether its option reached the
  target or the stop first, and how much of the move was already over when it appeared.
  A second way of deciding, which waits for the buying and selling pressure in the live
  order book to agree with the view before recommending inside the minute, runs silently
  beside the main one and is scored the same way; it takes over only when the scores show
  it is better.
- Around US economic data releases (inflation, jobs figures) a one-minute trend on gold
  and silver is mostly noise, so no metal recommendation is issued in a window around
  each release. The releases are kept in a list the trader edits by hand. The window can
  also end a recommendation already waiting and refuse a paper trade opened by hand, each
  as a choice in the configuration. The view is still worked out during the pause, and
  open trades are never touched.

### Paper trading
- Every active recommendation has a "Paper trade" action. Nothing happens unless the
  trader uses it.
- A paper trade opens at the price prevailing at the moment of the click, and records how
  far that was from the recommended entry; it takes the target and stop worked out at its
  own fill.
- Paper trades are funded by one paper bank account, shared by every market. Opening a
  trade blocks its money: an option's premium, or a future's margin, plus the round-trip
  cost. A trade the bank cannot fund is refused with the reason, and the recommendation
  stays on offer. When the trade closes, the money is released and its net profit or loss
  is paid in or taken out.
- The bank's opening balance is part of the configuration. Raising it pays in the
  difference and lowering it takes the difference out; profit and loss made so far keeps
  counting. A futures loss can be larger than its margin, so the balance can go below
  zero, and then no new trade opens until money is paid in or trades close.
- An open paper trade is tracked live and closes automatically when it reaches its target,
  hits its stop, or the end-of-day square-off time arrives. The trader can also close it
  by hand at any time, from the dashboard or from the Trades page.
- A paper trade cannot be opened or closed by hand while that market's live prices are
  unavailable, because there is no honest price to trade at.
- If the feed drops while a trade is open, target and stop are checked again from the
  first live price after it returns. A trade closed that way is marked as closed after a
  data gap.
- If the feed is still unavailable at square-off time, the trade is closed at the last
  price the app saw and marked as closed on a stale price, so nothing is hidden.
- Profit or loss is shown net of trading costs (brokerage, taxes, exchange charges), using
  a per-trade cost the trader can adjust; for a future the cost also grows with the value
  traded. The gross figure is shown alongside. Hit rate is based on the net figure.
- The **Journal** shows the paper bank (balance, money blocked by open trades, money free,
  and every payment in and out) and the summary: hit rate, average win, average loss, net
  result and how trades closed, for index options overall, per index, for bullion overall
  and per metal.
- The **Trades** page lists every paper trade. Open trades come first, at the current
  price, each with its profit or loss so far, the time held and a Close action. Closed
  trades follow, grouped by day, each day with its count, wins and losses and net result.
  The list can be narrowed by market, dates, how a trade closed, and whether its exit was
  on a live price. Any trade opens to show its levels and fills, its risk against reward
  and result, the recommendation it was taken on, what the contract did afterwards, and
  the evidence as it stood at that minute.

### The screen
- **Top bar**, in groups that look different from each other:
  - the app's name, which takes the trader back to the dashboard;
  - a status strip: whether the market on screen is open, with the time; whether the live
    data feed is healthy and how fresh it is; whether the daily broker login is valid;
  - on the right, the three pages (Dashboard, Journal, Trades, with the count of open
    trades on Trades), then the dashboard's own controls (restore minimised panels,
    show or hide the headlines), then the tools (Data, Configuration with the version in
    force, the latency overlay, light or dark), and last, on its own, Login or Logout.
  - It never scrolls sideways: on a narrow window it wraps onto a second line.
- **Dashboard**, switchable between NIFTY, BANK NIFTY and, when gold and silver data is
  available, BULLION (where the same panels follow the metal chosen with a switch):
  - a summary of the index, with a details view that can be opened and closed, showing
    the day's open, high and low and where the price sits in that range, the 52-week high
    and low, the previous close and the change on the day, the futures premium over the
    index, India VIX, and the at-the-money strike; below it, the sector indices (for NIFTY
    Auto, FMCG, IT, Pharma, Metal, Energy, Realty, Media, Financial Services and PSU Bank;
    for BANK NIFTY its bank sub-indices), each with its level and change, in a block that
    can be closed;
  - on BULLION instead, gold and silver side by side: the price and change on the day,
    and behind a details toggle the day's range, trading activity, the contract's range
    and price limits, the next month's price and the gap to it; and the gold/silver ratio;
  - the active recommendation, if any, with its details, live levels and the Paper trade
    action;
  - the market view: a bearish-to-bullish meter with its strength across the full width,
    with the evidence behind it underneath, each piece showing whether it is switched on;
    for an index, the order-flow reading below;
  - an intraday minute chart with the recommendation markers, and under it each minute's
    buying against selling volume of the near-month future (the metal's own future on
    BULLION), for display only;
  - the open paper trades with their live profit or loss and the paper bank, always on
    the page, saying so when none are open;
  - the day's recommendations, with how each one turned out.
- **Right-hand column**: a live option chain for the selected index and expiry, showing
  for each strike the call and put price, change, open interest, change in open interest,
  and implied volatility. The at-the-money strike is highlighted and heavy open-interest
  build-up is visually emphasised. The put-call ratio and max-pain level are shown at the
  top. Below the chain, the latest headlines, newest first and grouped by day, with new
  ones marked, the freshest in accent, and each stock tagged by the index it moves (never
  in green or red, which mean bullish and bearish here). Headlines are a quick check on
  what is moving the market, never an input to the recommendations. There is no chain on
  BULLION.
- **Journal** and **Trades** pages, as described under "Paper trading".
- **Configuration**: a panel on the right of the screen with three tabs: the values, each
  explained on the line below its name with its allowed range; the evidence switches, each
  with a one-line explanation; and the versions, with the one in force marked. The trader
  edits the values in the app and saves them under a tag of their own; each save is a
  numbered version, and so is each flip of an evidence switch. An invalid value is refused
  with the reason and the previous values stay. Any earlier version can be brought back.
  Every recommendation shows the version it was made under, and hovering it shows that
  version's values. The panel closes with a clear button, by clicking outside it, or with
  Escape.
- **Data**: an action to delete raw tick data up to and including a chosen date, which
  first shows how many days and how much space will be freed and asks for confirmation.
- Everything on screen updates live without the trader refreshing the page.
- The trader can resize the panels by dragging the borders between them (the main area
  against the right-hand column, the chart's height, the chain against the headlines),
  and the app remembers the layout. A panel cannot be dragged so small that it
  disappears, and double-clicking a border puts it back.
- Every panel can be minimised to a single line with a short summary, and expanded again
  where it was; a minimised recommendation or open-trades panel opens itself when a new
  recommendation arrives or a trade opens. The headlines can also be taken off the page
  and brought back. The right-hand column gives its space to the main area when both of
  its panels are put away. The app remembers all of this.
- The panels of the dashboard can be moved up and down into the order the trader
  prefers, each on its own; one control puts every panel back as it was, in the original
  order. The app remembers the order.
- Dates are shown as DD/MM/YYYY everywhere on screen.

### Operating hours
- The app follows NSE trading hours and holidays for the indices, and MCX's hours (to
  23:30, later in winter) and holidays for gold and silver. Each market is judged by its
  own hours: a market that has closed is not treated as a broken feed, and one market's
  ticks never make the other look live. The top bar and the banner follow the market on
  screen.
- Outside a market's hours the app shows its last known state and makes clear,
  prominently, that the market is closed.
- The broker feed requires a fresh login each day. When that login is missing or expired,
  the app says so clearly and keeps working with whatever it can, rather than failing.
  The trader can also log out at any time, which stops the live feed until the next login;
  logging in again restarts it without restarting the app.

## Out of scope
- News and FII/DII buying and selling as inputs to the market view (the model allows for
  them later; headlines are shown, but only for reading).
- Real order placement, including one-click or automatic ordering.
- Option selling, spreads, and multi-leg strategies.
- Stock options and other indices (FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX).
- Multiple users, logins, cloud hosting, mobile apps.
- Back-testing over historical data, beyond replaying recorded days (data is stored so
  this becomes possible).

Considered and left for later: zoom buttons on the charts; showing one panel full screen;
dragging panels to re-order them; recommending options a few strikes in or out of the
money instead of at the money (analysed in
[strike_ladder_analysis.md](strike_ladder_analysis.md)); more evidence for gold and
silver (MCX options, multi-day levels, international prices).

## Assumptions and defaults chosen during planning
These were set by the planner, not the trader, and can be changed:
- Strikes covered: ten either side of the current level.
- Default target and stop: +30% and −15% of the option premium.
- A recommendation lapses after five minutes if not paper-traded.
- Indices: no new recommendations after 15:00; open paper trades square off at 15:15.
- Paper trades are one lot each.
- Default round-trip trading cost per lot: ₹60; for a future, also 0.012 % of the value
  traded.
- Expiry-day target and stop in index points: 40 / 20 for NIFTY, 100 / 50 for BANK NIFTY.
- Other markets carry 10 % of an index's view; GIFT Nifty's gap fades over 30 minutes, and
  the view follows the gap rather than fading it.
- Gold and silver: a recommendation needs a stronger view than for the indices (0.60
  against 0.50); target and stop are 0.40 % and 0.20 % of the future's price;
  recommendations from 09:15 to 22:45, square-off at 23:00. Price trend carries 60 % of
  the view, open interest and order flow 15 % each, other markets 10 %. The view is worked
  out 20 seconds after each minute so it never competes with the index work.
- US data releases pause metal recommendations from 15 minutes before to 15 minutes after;
  ending a waiting recommendation and refusing a manual paper trade during the pause are
  both off. Release times are written in IST by hand, as MCX's winter close is changed by
  hand.
- The paper bank opens with ₹25 lakh. A gold future blocks 10 % of its value, a silver
  future 12 %.
- Headlines are asked for every three minutes while logged in.
- When the app is started after market open, it fills in the morning's data so that its
  view is valid immediately rather than after a warm-up.
- Raw tick data is kept until the trader deletes it; nothing is pruned automatically.
- The right-hand column starts shown; the index details view starts closed and the
  sectors block open. These choices, the panel sizes, the order and what is minimised are
  remembered on the trader's computer.
- The 52-week high and low are worked out from a year of daily prices from the broker and
  include today.

## Before building can be tested live
- The trader opens a broker account with a free, official data API (Upstox is the chosen
  provider) and registers an API application to obtain credentials.
