import type {
  BiasOut,
  CandleOut,
  ChainOut,
  IndexPrices,
  IndexStatsOut,
  PaperTradeOut,
  SignalOut,
} from '../api/types'
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
  const side = signal.direction === 'BUY_CE' ? 'CE' : 'PE'
  return `${String(signal.strike)} ${side} · entry ${fmtPrice(signal.entry_price)} · ${countdown(signal.expires_at, now)} left`
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

export function evidenceSummary(bias: BiasOut | undefined): string {
  return bias ? `bias ${fmtSigned(bias.bias, 3)}` : '—'
}

export function historySummary(signals: SignalOut[], index: string): string {
  return `${String(signals.filter((s) => s.index === index).length)} today`
}

export function chainSummary(chain: ChainOut | undefined): string {
  if (!chain) return '—'
  const pcr = chain.pcr == null ? '—' : chain.pcr.toFixed(2)
  const pain = chain.max_pain == null ? '—' : String(chain.max_pain)
  return `PCR ${pcr} · max pain ${pain}`
}
