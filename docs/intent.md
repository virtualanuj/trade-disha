# TradeDisha — Intent and Requirements

## Purpose

TradeDisha is a personal trading assistant for NSE index options. During market hours it
watches the market continuously, forms a view on whether the market is turning bullish or
bearish, and when that view is strong enough it recommends a specific option to buy. Every
recommendation comes with the reasons behind it, so the trader can judge it rather than
follow it blindly.

The trader places real orders themselves in their broker's app. TradeDisha never places a
real order. It does offer paper trading, so the trader can test the recommendations with
virtual money and build a track record of how well they work.

## Who it is for

A single trader, running the application on their own computer, looking at it in a web
browser through the trading day. There are no other users, no accounts to manage, and no
hosting.

## What success looks like

- The trader opens the app in the morning and, within a minute, sees the live state of the
  market and a live option chain without needing to look anywhere else.
- When the app recommends a trade, the trader can see in one glance what the recommendation
  is, why it was made, and what entry, target, and stop it suggests.
- The trader can paper-trade a recommendation with one click and later see how it played
  out, alongside every other paper trade, with overall hit rate and profit or loss.
- Over weeks of use, the paper-trade journal gives an honest answer to the question "are
  these signals worth real money?"

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
   smoothly and continuously; the page never freezes, flickers, or needs a refresh.
2. **Low latency.** A change in the market should be visible on screen within a quarter of
   a second of it reaching the application, and a new recommendation should appear within
   a tenth of a second of the app seeing the minute close. The delay between the broker and
   the application is outside the app's control, but it is measured and shown so the trader
   always knows how fresh the data is. The app must stay this responsive for a full trading
   day without slowing down.
3. **Clean, maintainable code.** The code is written so that a competent developer who has
   never seen it can read it, change it, and trust it: small well-named parts, automated
   tests for all the trading logic, consistent style enforced by tools, and no hidden
   behaviour.
4. **Tunable signal algorithm.** Everything that shapes a recommendation — the weight of
   each kind of evidence, the thresholds, the indicator settings, targets and stops,
   time cut-offs — lives in one plain configuration file that the trader edits. The app
   runs from that single file. If the file is changed during a session, the trader can
   reload it from the app without restarting, and the new values take effect from the
   next minute.

## Scope of the first version

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

### Data
- Live prices and open interest from a reliable, official broker data feed that is free to
  use with a broker account.
- No scraping of websites, no unofficial feeds, no delayed data presented as live.
- Market data, the app's own calculations, recommendations, and paper trades are all kept
  on the trader's computer so past days can be reviewed later.
- Raw tick data is the bulky part. The trader can delete raw ticks up to and including a
  chosen date from within the app to free disk space. Everything derived from them
  (minute candles, option-chain history, market views, recommendations, paper trades) is
  always kept.

### Market view (bias)
- For each index, the app maintains a continuously updated view: bullish, neutral, or
  bearish, with a strength.
- The view is refreshed every minute during market hours.
- The view is built from three kinds of evidence:
  1. **Price trend** — the direction and momentum of the index itself.
  2. **Open interest** — where positions are building up in the option chain, the balance
     between puts and calls, and how that is shifting.
  3. **Premium behaviour** — whether call and put premiums, and their implied volatility,
     agree with the move in the index.
- Each kind of evidence contributes a vote and a weight. The trader can see every vote.
- The model must be able to take on further kinds of evidence later, in particular news
  flow and FII/DII buying and selling. These are not part of the first version.

### Recommendations (signals)
- When the view for an index becomes strong enough, the app issues a recommendation: buy a
  specific call option (bullish) or a specific put option (bearish), at the strike closest
  to the current index level.
- The first version recommends buying options only. No selling, no spreads, no multi-leg
  strategies.
- A recommendation states: the index, the exact option (strike, expiry, call or put), a
  suggested entry price, a target, a stop, the time it was issued, and a breakdown of the
  evidence that produced it.
- Only one recommendation per index is active at a time.
- A recommendation lapses if it is not acted on within a short window, or if the market
  view reverses or weakens back to neutral.
- If the view is still strong enough when a recommendation ends (taken or lapsed), a fresh
  recommendation is issued at the current price. The trader is never left without a
  current recommendation while the view supports one.
- Open paper trades never block recommendations, in either direction. Whenever a
  recommendation is issued while paper trades are open on that index, it prominently shows
  the key facts of each open trade (which option, entry price, current profit or loss,
  time held) so the trader can decide whether to close one first.
- An open paper trade is flagged "view reversed" whenever the current view opposes it, and
  the flag clears if the view comes back.
- No new recommendations are issued in the final part of the trading day, so that trades
  are not opened with too little time left.

### Paper trading
- Every active recommendation has a "Paper trade" action. Nothing happens unless the
  trader uses it.
- A paper trade opens at the price prevailing at the moment of the click, and records how
  far that was from the recommended entry.
- An open paper trade is tracked live and closes automatically when it reaches its target,
  hits its stop, or the end-of-day square-off time arrives. The trader can also close it
  by hand at any time.
- Only trades the trader actually clicked are tracked. Recommendations that lapse untraded
  are kept as a record of the recommendation only; the app does not work out what would
  have happened to them.
- A paper trade cannot be opened while the live feed is unavailable, because there is no
  honest price to open it at.
- If the feed drops while a trade is open, target and stop are checked again from the
  first live price after it returns. A trade closed that way is marked as closed after a
  data gap.
- If the feed is still unavailable at square-off time, the trade is closed at the last
  price the app saw and marked as closed on a stale price, so the journal never hides it.
- Profit or loss is shown net of trading costs (brokerage, taxes, exchange charges), using
  a per-trade cost the trader can adjust. The gross figure is shown alongside. Hit rate is
  based on the net figure.
- A journal lists all paper trades with entry, exit, gross and net profit or loss, how long
  the trade lasted, why it closed, and the recommendation that started it.
- The journal summarises hit rate, average win, average loss, and net result, overall and
  per index.

### The screen
- **Top bar**: whether the market is open, whether the live data feed is healthy and how
  fresh it is, and whether the daily broker login has been done, with a way to do it.
- **Main area**, switchable between NIFTY and BANK NIFTY:
  - a summary of the index with a details view that can be opened and closed, showing the
    day's open, high and low and where the price sits in that range, the 52-week high and
    low, the previous close and the change on the day, the futures premium over the index,
    and India VIX,
  - the current market view as a bearish-to-bullish meter with its strength,
  - an intraday price chart of the index with recommendation markers,
  - the active recommendation, if any, with its details and the Paper trade action,
  - the evidence breakdown behind the current view.
- **Right-hand panel**: a live option chain for the selected index and expiry, showing for
  each strike the call and put price, change, open interest, change in open interest, and
  implied volatility. The at-the-money strike is highlighted and heavy open-interest
  build-up is visually emphasised. The put-call ratio and max-pain level are shown at the
  top of the panel.
- **Journal page**: the paper-trade list and summary.
- **Configuration**: the top bar shows when the configuration was last loaded and a
  "Reload config" action. Reloading validates the file first; if it is invalid the app
  says what is wrong and keeps the previous values.
- **Data**: an action to delete raw tick data up to and including a chosen date, which
  first shows how many days and how much space will be freed and asks for confirmation.
- Everything on screen updates live without the trader refreshing the page.
- The trader can resize the panels by dragging the borders between them, and the app
  remembers the layout the next time it is opened.
- The right-hand panel can be hidden to give the main area the full width, and shown
  again with one click. The app remembers which.
- Every panel can be minimised to a single line with a short summary, and expanded again
  where it was. The app remembers which are minimised.
- Open paper trades have their own panel that is always on the page, just above the list
  of the day's recommendations; it says so when none are open.
- Dates are shown as DD/MM/YYYY everywhere on screen.

### Operating hours
- The app is active from market open to market close on NSE trading days.
- Outside those hours it shows the last known state and makes clear the market is closed.
- The broker feed requires a fresh login each day. When that login is missing or expired,
  the app says so clearly and keeps working with whatever it can, rather than failing.

## Enhancements after the first version

Requested once the first version was in daily use. They change how the screen looks and
what it shows; they do not change how the market view, recommendations or paper trades
work.

1. **Resizable panels.** The borders between the main area and the option chain, and
   under the price chart, can be dragged. The layout is remembered.
2. **Hideable right-hand panel.** The option-chain panel can be hidden and shown again;
   the choice is remembered. Hiding it changes nothing about how the option chain feeds
   the market view.
3. **DD/MM/YYYY dates.** Every date on screen uses this format.
4. **Index details view.** The index summary at the top of the main area opens to show the
   day's open, high and low with the position in the day's range, the 52-week high and low,
   the previous close and change on the day, the futures premium over the index, and
   India VIX. It applies to NIFTY and BANK NIFTY alike.

5. **Minimisable panels.** Every panel on the main screen can be minimised to a single
   line, showing a short summary, to make room for the others, and expanded again where
   it was. A minimised recommendation panel opens itself when a new recommendation
   arrives. Minimised panels are remembered. The open paper trades panel is always on the
   page, second last, just above the day's recommendations.

Considered and left for later: zoom-in and zoom-out buttons on the charts; showing one
panel full screen (built, then removed at the owner's request); dragging panels to
re-order them.

## Explicitly out of scope for the first version
- News and FII/DII inputs (planned next).
- Real order placement, including one-click or automatic ordering.
- Option selling, spreads, and multi-leg strategies.
- Stock options and other indices (FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX).
- Multiple users, logins, cloud hosting, mobile apps.
- Back-testing over historical data (though data is stored so this becomes possible later).

## Assumptions and defaults chosen during planning
These were set by the planner, not the trader, and can be changed:
- Strikes covered: ten either side of the current level.
- Default target and stop: +30% and −15% of the option premium.
- A recommendation lapses after five minutes if not paper-traded.
- No new recommendations after 15:00; open paper trades square off at 15:15.
- Paper trades are one lot each.
- Default round-trip trading cost per lot: ₹60.
- Expiry-day target and stop in index points: 40 / 20 for NIFTY, 100 / 50 for BANK NIFTY.
- When the app is started after market open, it fills in the morning's data so that its
  view is valid immediately rather than after a warm-up.
- Raw tick data is kept until the trader deletes it; nothing is pruned automatically.
- The right-hand panel starts shown.
- The index details view starts closed. Whether it is open, and the panel sizes, are
  remembered on the trader's computer.
- A panel cannot be dragged so small that it disappears; double-clicking a border puts it
  back to its original position.
- The 52-week high and low are worked out from a year of daily prices from the broker and
  include today.

## Before building can be tested live
- The trader opens a broker account with a free, official data API (Upstox is the chosen
  provider) and registers an API application to obtain credentials.
