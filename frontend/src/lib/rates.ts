import type { BullionOut, IndexPrices, IndexStatsOut, QuoteOut } from '../api/types'
import { ETF_TAB } from '../state/store'

/** One entry on the rates strip (E26). `tab` is where a click goes; null: not clickable. */
export interface Rate {
  name: string
  ltp: number | null
  changePct: number | null
  tab: string | null
}

const METAL_ORDER = ['GOLD', 'SILVER'] as const

function pct(ltp: number | null, prev: number | null | undefined): number | null {
  return ltp == null || !prev ? null : Math.round(((ltp - prev) / prev) * 10000) / 100
}

/**
 * NIFTY, SENSEX, GOLD, SILVER, GOLDBEES, SILVERBEES, in that order, always all six; a rate
 * not known yet is null. NIFTY is the live spot against the stats' previous close, so it
 * moves with the Index tile. A click opens the tab (E32): a metal its MCX tab, an ETF NSE's
 * BULLION; a tab not in `tabs` (no data for it) is not offered.
 */
export function stripRates(
  nifty: IndexPrices | undefined,
  niftyStats: IndexStatsOut | undefined,
  quotes: QuoteOut[],
  bullion: BullionOut | null,
  tabs: readonly string[],
): Rate[] {
  const offered = (tab: string): string | null => (tabs.includes(tab) ? tab : null)
  const ltp = nifty?.spot_ltp ?? null
  const sensex = quotes.find((q) => q.name === 'SENSEX')
  const rates: Rate[] = [
    {
      name: 'NIFTY',
      ltp,
      changePct: pct(ltp, niftyStats?.prev_close),
      tab: offered('NIFTY'),
    },
    {
      name: 'SENSEX',
      ltp: sensex?.ltp ?? null,
      changePct: sensex?.change_pct ?? null,
      tab: null,
    },
  ]
  for (const metal of METAL_ORDER) {
    const m = bullion?.metals.find((x) => x.metal === metal)
    rates.push({
      name: metal,
      ltp: m?.ltp ?? null,
      changePct: m?.change_pct ?? null,
      tab: offered(metal),
    })
  }
  for (const metal of METAL_ORDER) {
    const e = bullion?.etfs.find((x) => x.metal === metal)
    rates.push({
      name: e?.symbol ?? `${metal}BEES`,
      ltp: e?.ltp ?? null,
      changePct: e?.change_pct ?? null,
      tab: offered(ETF_TAB),
    })
  }
  return rates
}
