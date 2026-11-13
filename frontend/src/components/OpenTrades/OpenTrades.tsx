import { useState } from 'react'

import { closePaperTrade } from '../../api/client'
import type { PaperTradeOut } from '../../api/types'
import { fmtDuration, fmtIstTime, fmtMoney, fmtPrice, pnlColour } from '../../lib/format'

interface Props {
  /** open trades on the selected index */
  trades: PaperTradeOut[]
  now: number
  /** false while the feed is down: closing needs a live price */
  canClose: boolean
  onClose?: (tradeId: string) => Promise<unknown>
}

/** Open paper trades with live P&L. Always visible while any are open, signal or not. */
export function OpenTrades({ trades, now, canClose, onClose = closePaperTrade }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  if (trades.length === 0) return null

  const close = (id: string) => {
    setBusy(id)
    setError(null)
    onClose(id)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'could not close')
      })
      .finally(() => {
        setBusy(null)
      })
  }

  return (
    <div
      className="rounded border border-accent/50 bg-bg-elev p-3 text-xs"
      data-testid="open-trades"
    >
      <div className="mb-2 text-[10px] uppercase tracking-wide text-fg-muted">
        Open paper trades · {trades.length}
      </div>
      <table className="w-full font-mono">
        <thead className="text-fg-muted">
          <tr className="h-6 font-sans">
            <th className="text-left font-normal">Option</th>
            <th className="text-right font-normal">Entry</th>
            <th className="text-right font-normal">Now</th>
            <th className="text-right font-normal">Target</th>
            <th className="text-right font-normal">Stop</th>
            <th className="text-right font-normal">Net P&amp;L</th>
            <th className="text-right font-normal">Open for</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="h-7 border-t border-border/60">
              <td className={t.direction === 'BUY_CE' ? 'text-bull' : 'text-bear'}>
                {t.strike} {t.direction === 'BUY_CE' ? 'CE' : 'PE'}
                <span className="ml-1 text-fg-muted">×{t.qty}</span>
                {t.warning === 'bias_reversed' ? (
                  <span
                    className="ml-2 rounded bg-warn/20 px-1 font-sans text-warn"
                    title="The current market view opposes this trade. Nothing is closed for you."
                  >
                    bias reversed
                  </span>
                ) : null}
              </td>
              <td className="text-right" title={`opened ${fmtIstTime(t.entry_ts)}`}>
                {fmtPrice(t.entry_price)}
              </td>
              <td className="text-right">{fmtPrice(t.ltp)}</td>
              <td className="text-right text-bull">{fmtPrice(t.target_price)}</td>
              <td className="text-right text-bear">{fmtPrice(t.stop_price)}</td>
              <td
                className={`text-right ${pnlColour(t.live_net)}`}
                title={`gross ${fmtMoney(t.live_gross)}, cost ₹${String(t.cost)}`}
              >
                {fmtMoney(t.live_net)}
              </td>
              <td className="text-right text-fg-muted">{fmtDuration(now - t.entry_ts)}</td>
              <td className="text-right font-sans">
                <button
                  type="button"
                  className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg disabled:opacity-50"
                  disabled={!canClose || busy === t.id}
                  title={
                    canClose ? 'Close at the current price' : 'Feed not live: no price to close at'
                  }
                  onClick={() => {
                    close(t.id)
                  }}
                >
                  {busy === t.id ? 'Closing…' : 'Close'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {error ? (
        <div className="mt-2 text-bear" role="alert">
          Not closed: {error}
        </div>
      ) : null}
    </div>
  )
}
