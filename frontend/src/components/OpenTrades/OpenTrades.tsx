import { Fragment, useState } from 'react'

import { closePaperTrade } from '../../api/client'
import type { PaperTradeOut } from '../../api/types'
import { instrumentLabel, isLong } from '../../lib/direction'
import { fmtDuration, fmtIstTime, fmtMoney, fmtPrice, fmtRupees, pnlColour } from '../../lib/format'
import { useInFlight } from '../../lib/useInFlight'
import { LevelsEditor } from '../LevelsEditor/LevelsEditor'

interface Props {
  /** open trades on the selected index */
  trades: PaperTradeOut[]
  now: number
  /** false while the feed is down: closing needs a live price */
  canClose: boolean
  onClose?: (tradeId: string) => Promise<unknown>
  saveLevels?: (tradeId: string, target: number, stop: number) => Promise<unknown>
}

const COLUMNS = 9

/** Opened by hand, with no signal (E23). */
export function ManualBadge() {
  return (
    <span
      className="ml-2 rounded bg-accent/15 px-1 font-sans text-accent"
      title="Opened by hand, with no signal"
    >
      manual
    </span>
  )
}

/** Open paper trades with live P&L. Always on the page, signal or not; says so when none are open. */
export function OpenTrades({
  trades,
  now,
  canClose,
  onClose = closePaperTrade,
  saveLevels,
}: Props) {
  const { busy, errors, run } = useInFlight()
  const [editing, setEditing] = useState<string | null>(null)
  if (trades.length === 0) {
    return (
      <div className="text-xs text-fg-muted" data-testid="open-trades">
        No open paper trades.
      </div>
    )
  }

  const close = (id: string) => {
    run(id, () => onClose(id), 'could not close')
  }
  const refused = trades.filter((t) => errors[t.id] !== undefined)

  return (
    <div className="text-xs" data-testid="open-trades">
      <table className="w-full font-mono">
        <thead className="text-fg-muted">
          <tr className="h-6 font-sans">
            <th className="text-left font-normal">Option</th>
            <th className="text-right font-normal">Entry</th>
            <th className="text-right font-normal">Now</th>
            <th className="text-right font-normal">Target</th>
            <th className="text-right font-normal">Stop</th>
            <th className="text-right font-normal">Net P&amp;L</th>
            <th
              className="text-right font-normal"
              title="Held in the paper bank while open: premium or margin, plus cost"
            >
              Blocked
            </th>
            <th className="text-right font-normal">Open for</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <Fragment key={t.id}>
              <tr className="h-7 border-t border-border/60">
                <td className={isLong(t.direction) ? 'text-bull' : 'text-bear'}>
                  {instrumentLabel(t)}
                  <span className="ml-1 text-fg-muted">×{t.qty}</span>
                  {t.manual ? <ManualBadge /> : null}
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
                <td
                  className="text-right text-bull"
                  title={t.levels_edited ? 'Changed since the trade opened' : undefined}
                >
                  {fmtPrice(t.target_price)}
                  {t.levels_edited ? '*' : ''}
                </td>
                <td
                  className="text-right text-bear"
                  title={t.levels_edited ? 'Changed since the trade opened' : undefined}
                >
                  {fmtPrice(t.stop_price)}
                  {t.levels_edited ? '*' : ''}
                </td>
                <td
                  className={`text-right ${pnlColour(t.live_net)}`}
                  title={`gross ${fmtMoney(t.live_gross)}, cost ₹${String(t.cost)}`}
                >
                  {fmtMoney(t.live_net)}
                </td>
                <td className="text-right text-fg-muted">{fmtRupees(t.blocked)}</td>
                <td className="text-right text-fg-muted">{fmtDuration(now - t.entry_ts)}</td>
                <td className="whitespace-nowrap text-right font-sans">
                  <button
                    type="button"
                    className="mr-1 rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg disabled:opacity-50"
                    disabled={!canClose}
                    aria-expanded={editing === t.id}
                    title={
                      canClose
                        ? 'Change the target and stop'
                        : 'Feed not live: no price to check against'
                    }
                    onClick={() => {
                      setEditing(editing === t.id ? null : t.id)
                    }}
                  >
                    Levels
                  </button>
                  <button
                    type="button"
                    className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg disabled:opacity-50"
                    disabled={!canClose || busy.has(t.id)}
                    title={
                      canClose
                        ? 'Close at the current price'
                        : 'Feed not live: no price to close at'
                    }
                    onClick={() => {
                      close(t.id)
                    }}
                  >
                    {busy.has(t.id) ? 'Closing…' : 'Close'}
                  </button>
                </td>
              </tr>
              {editing === t.id ? (
                <tr>
                  <td colSpan={COLUMNS}>
                    <LevelsEditor
                      trade={t}
                      onDone={() => {
                        setEditing(null)
                      }}
                      {...(saveLevels ? { save: saveLevels } : {})}
                    />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
      {refused.map((t) => (
        <div key={t.id} className="mt-2 text-bear" role="alert">
          Not closed: {errors[t.id]} <span className="text-fg-muted">({instrumentLabel(t)})</span>
        </div>
      ))}
    </div>
  )
}

/**
 * The Trades tab's hover card (E27): every open trade, all markets, one line each with its
 * live net P&L, and the total. Read only: closing and levels stay on the panel and the page.
 */
export function OpenTradesPeek({ trades }: { trades: PaperTradeOut[] }) {
  const open = trades.filter((t) => t.status === 'open')
  if (open.length === 0) {
    return (
      <div className="text-fg-muted" data-testid="trades-peek">
        No open paper trades.
      </div>
    )
  }
  const total = open.reduce((sum, t) => sum + (t.live_net ?? 0), 0)
  const known = open.some((t) => t.live_net != null)
  return (
    <div data-testid="trades-peek">
      <div className="mb-1 font-semibold">Open paper trades ({open.length})</div>
      <table className="font-mono">
        <tbody>
          {open.map((t) => (
            <tr key={t.id} className="h-5">
              <td className={`pr-3 ${isLong(t.direction) ? 'text-bull' : 'text-bear'}`}>
                {t.index} {instrumentLabel(t)}
                <span className="ml-1 text-fg-muted">×{t.qty}</span>
              </td>
              <td className="pr-3 text-right whitespace-nowrap">
                {fmtPrice(t.entry_price)} → {fmtPrice(t.ltp)}
              </td>
              <td className={`text-right ${pnlColour(t.live_net)}`}>{fmtMoney(t.live_net)}</td>
            </tr>
          ))}
          <tr className="h-6 border-t border-border/60">
            <td className="pr-3 font-sans text-fg-muted" colSpan={2}>
              Total net P&amp;L
            </td>
            <td className={`text-right font-semibold ${pnlColour(known ? total : null)}`}>
              {fmtMoney(known ? total : null)}
            </td>
          </tr>
        </tbody>
      </table>
      <div className="mt-2 text-fg-muted">Click for the Trades page.</div>
    </div>
  )
}
