import type {
  BiasOut,
  BullionEtfOut,
  BullionOut,
  CandleOut,
  ChainOut,
  IndexPrices,
  IndexStatsOut,
  PaperTradeOut,
  SignalOut,
} from '../api/types'
import { instrumentLabel } from './direction'
import { countdown, fmtMoney, fmtPrice, fmtSigned } from './format'

/** One line per panel, shown on its title bar while it is minimised. Unknowns read "—". */

export function tilesSummary(
  prices: IndexPrices | undefined,
  stats: IndexStatsOut | undefined,
): string {
  if (prices?.spot_ltp == null) return '—'
  const spot = fmtPrice(prices.spot_ltp)
  return stats?.change_pct == null ? spot : `${spot} · ${fmtSigned(stats.change_pct, 2)}%`
}

export function biasSummary(bias: BiasOut | undefined): string {
  return bias ? `${String(bias.strength)} ${bias.label}` : '—'
}

export function signalSummary(signal: SignalOut | undefined, now: number): string {
  if (!signal) return 'No signal'
  return `${instrumentLabel(signal)} · entry ${fmtPrice(signal.entry_price)} · ${countdown(signal.expires_at, now)} left`
}

/** Live net profit or loss across the trades; null until every one has a price. */
export function openPnl(trades: PaperTradeOut[]): number | null {
  let total = 0
  for (const t of trades) {
    if (t.live_net == null) return null
    total += t.live_net
  }
  return trades.length ? total : null
}

export function tradesSummary(trades: PaperTradeOut[]): string {
  if (trades.length === 0) return 'None open'
  return `${String(trades.length)} open · ${fmtMoney(openPnl(trades))}`
}

export function chartSummary(candles: CandleOut[]): string {
  const last = candles.at(-1)
  return last ? `last ${fmtPrice(last.c)}` : '—'
}

export function historySummary(signals: SignalOut[], index: string): string {
  const mine = signals.filter((s) => s.index === index)
  const shadow = mine.filter((s) => s.shadow).length
  return `${String(mine.length - shadow)} today` + (shadow ? ` · ${String(shadow)} shadow` : '')
}

export function chainSummary(chain: ChainOut | undefined): string {
  if (!chain) return '—'
  const pcr = chain.pcr == null ? '—' : chain.pcr.toFixed(2)
  const pain = chain.max_pain == null ? '—' : String(chain.max_pain)
  return `PCR ${pcr} · max pain ${pain}`
}

/** A bullion tiles panel minimised: its metal's (or every metal's) prices and the ratio. */
export function bullionSummary(bullion: BullionOut | null, metal?: string): string {
  const all = bullion?.metals ?? []
  const metals = metal === undefined ? all : all.filter((m) => m.metal === metal)
  if (metals.length === 0) return '—'
  const parts = metals.flatMap((m) => [
    `${m.metal} ${fmtPrice(m.ltp)}`,
    ...(m.mini ? [`${m.mini.metal} ${fmtPrice(m.mini.ltp)}`] : []),
  ])
  if (bullion?.ratio != null) parts.push(`ratio ${bullion.ratio.toFixed(2)}`)
  return parts.join(' · ')
}

/** The ETF panel minimised (E32): each ETF's price. */
export function etfSummary(etfs: BullionEtfOut[]): string {
  return etfs.length === 0 ? '—' : etfs.map((e) => `${e.symbol} ${fmtPrice(e.ltp)}`).join(' · ')
}
