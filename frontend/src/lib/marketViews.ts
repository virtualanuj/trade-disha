import type { BullionOut, IndexPrices, PaperTradeOut } from '../api/types'

/**
 * Small values read out of the store. A selector that returns one of these re-renders its
 * component only when the value changes, not on every frame that replaces the slice.
 */

/** the newest spot or future tick of any index, for the top bar's feed age */
export function newestIndexTickTs(prices: Record<string, IndexPrices>): number | null {
  let latest: number | null = null
  for (const p of Object.values(prices)) {
    for (const ts of [p.spot_ts, p.fut_ts]) {
      if (ts != null && (latest == null || ts > latest)) latest = ts
    }
  }
  return latest
}

/** on the BULLION tab the feed age measures MCX ticks, which run to 23:30 */
export function newestBullionTs(bullion: BullionOut | null): number | null {
  const stamps = (bullion?.metals ?? []).map((m) => m.updated_ts).filter((t) => t != null)
  return stamps.length ? Math.max(...stamps) : null
}

export function openTradeCount(trades: PaperTradeOut[]): number {
  return trades.reduce((n, t) => n + (t.status === 'open' ? 1 : 0), 0)
}

/** changes whenever a trade opens or closes (not on live P&L), so the pages refetch */
export function tradeRevision(trades: PaperTradeOut[]): number {
  return trades.reduce((n, t) => n + (t.status === 'closed' ? 2 : 1), 0)
}
