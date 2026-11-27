import type { ExitReason, PaperTradeOut } from '../api/types'
import { METAL_TABS } from '../state/store'

/**
 * The Trades page's summary, worked out from the trades the table shows, so it follows
 * every filter (E26). Only closed trades make the results; open ones are counted apart
 * with their live P&L. A win is a positive net, as on the server (`/journal/stats`).
 */
export interface TradeSummary {
  closed: number
  wins: number
  losses: number
  hitRate: number | null
  net: number
  gross: number
  cost: number
  avgWin: number | null
  avgLoss: number | null
  /** money won over money lost; null with no losses */
  profitFactor: number | null
  /** net per closed trade */
  expectancy: number | null
  /** mean of each trade's net over its risk (fill to stop, times quantity) */
  avgR: number | null
  best: PaperTradeOut | null
  worst: PaperTradeOut | null
  /** the deepest fall of the running net, in exit order, from a peak (start counts as 0) */
  maxDrawdown: number
  /** the most losses in a row, in exit order */
  lossStreak: number
  avgHeldMs: number | null
  byReason: Partial<Record<ExitReason, number>>
  /** exits not filled on a live price */
  nonLive: number
  open: number
  unrealised: number
}

const mean = (xs: number[]): number | null =>
  xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null
const sum = (xs: number[]): number => xs.reduce((a, b) => a + b, 0)

function rOf(t: PaperTradeOut): number | null {
  const risk = Math.abs(t.entry_price - t.stop_price) * t.qty
  return risk > 0 && t.net != null ? t.net / risk : null
}

export function summarise(trades: PaperTradeOut[]): TradeSummary {
  const open = trades.filter((t) => t.status === 'open')
  const closed = trades
    .filter((t) => t.status !== 'open' && t.net != null)
    .sort((a, b) => (a.exit_ts ?? a.entry_ts) - (b.exit_ts ?? b.entry_ts))
  const nets = closed.map((t) => t.net ?? 0)
  const won = nets.filter((n) => n > 0)
  const lost = nets.filter((n) => n <= 0)

  let run = 0
  let peak = 0
  let maxDrawdown = 0
  let streak = 0
  let lossStreak = 0
  for (const n of nets) {
    run += n
    peak = Math.max(peak, run)
    maxDrawdown = Math.max(maxDrawdown, peak - run)
    streak = n > 0 ? 0 : streak + 1
    lossStreak = Math.max(lossStreak, streak)
  }

  const byReason: Partial<Record<ExitReason, number>> = {}
  for (const t of closed) {
    if (t.exit_reason) byReason[t.exit_reason] = (byReason[t.exit_reason] ?? 0) + 1
  }
  const lostSum = -sum(lost.filter((n) => n < 0))
  const rs = closed.map(rOf).filter((r): r is number => r !== null)
  const held = closed.filter((t) => t.exit_ts != null).map((t) => (t.exit_ts ?? 0) - t.entry_ts)
  const pick = (better: (a: number, b: number) => boolean) =>
    closed.reduce<PaperTradeOut | null>(
      (x, t) => (x === null || better(t.net ?? 0, x.net ?? 0) ? t : x),
      null,
    )

  return {
    closed: closed.length,
    wins: won.length,
    losses: lost.length,
    hitRate: closed.length ? won.length / closed.length : null,
    net: sum(nets),
    gross: sum(closed.map((t) => t.gross ?? 0)),
    cost: sum(closed.map((t) => t.cost)),
    avgWin: mean(won),
    avgLoss: mean(lost.filter((n) => n < 0)),
    profitFactor: lostSum > 0 ? sum(won) / lostSum : null,
    expectancy: mean(nets),
    avgR: mean(rs),
    best: pick((a, b) => a > b),
    worst: pick((a, b) => a < b),
    maxDrawdown,
    lossStreak,
    avgHeldMs: mean(held),
    byReason,
    nonLive: closed.filter((t) => t.exit_fill_quality && t.exit_fill_quality !== 'live').length,
    open: open.length,
    unrealised: sum(open.map((t) => t.live_net ?? 0)),
  }
}

export interface SummaryScope {
  key: string
  label: string
  /** a group total (index options, bullion, by hand), not one market */
  total: boolean
  summary: TradeSummary
}

/**
 * As the server splits them: index options and each index, bullion and each metal, from
 * signal trades; then the trades opened by hand, kept apart so the rest measure the
 * signals. Groups with no trades are left out, and a group is split only when it has more
 * than one market.
 */
export function summaryScopes(trades: PaperTradeOut[]): SummaryScope[] {
  const manual = trades.filter((t) => t.manual)
  const signalled = trades.filter((t) => !t.manual)
  const options = signalled.filter((t) => !METAL_TABS.includes(t.index))
  const bullion = signalled.filter((t) => METAL_TABS.includes(t.index))
  const out: SummaryScope[] = []
  const group = (key: string, label: string, list: PaperTradeOut[], split: boolean) => {
    if (list.length === 0) return
    out.push({ key, label, total: true, summary: summarise(list) })
    const markets = [...new Set(list.map((t) => t.index))].sort()
    if (!split || markets.length < 2) return // one market would repeat its group's row
    for (const m of markets) {
      const mine = list.filter((t) => t.index === m)
      out.push({ key: m, label: m, total: false, summary: summarise(mine) })
    }
  }
  group('overall', 'Index options', options, true)
  group('bullion', 'Bullion', bullion, true)
  group('manual', 'Opened by hand', manual, false)
  return out
}
