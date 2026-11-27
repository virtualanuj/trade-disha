import { memo, useMemo } from 'react'
import type { ReactNode } from 'react'

import type { ExitReason, PaperTradeOut } from '../../api/types'
import { instrumentName, sideTag } from '../../lib/direction'
import { fmtDuration, fmtMoney, fmtSigned, pnlColour } from '../../lib/format'
import { REASON_TEXT } from '../../lib/tradeText'
import { summarise, summaryScopes } from '../../lib/tradeStats'
import type { SummaryScope, TradeSummary as Summary } from '../../lib/tradeStats'

interface Props {
  /** the trades the table shows, after every filter: open ones and closed ones */
  trades: PaperTradeOut[]
}

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)
const ratio = (v: number | null) => (v == null ? '—' : v.toFixed(2))
const rText = (v: number | null) => (v == null ? '—' : `${fmtSigned(v, 2)}R`)
const tradeName = (t: PaperTradeOut) => `${t.index} ${instrumentName(t)} ${sideTag(t.direction)}`

/**
 * The summary at the head of the Trades table (E26): the headline figures for the trades
 * shown, then the same figures by market. Worked out from the table's own rows, so it
 * moves with every filter, Exit and Fill included.
 */
export const TradeSummary = memo(function TradeSummary({ trades }: Props) {
  const all = useMemo(() => summarise(trades), [trades])
  const scopes = useMemo(() => summaryScopes(trades), [trades])
  if (all.closed === 0 && all.open === 0) return null
  return (
    <div className="flex flex-col gap-3" data-testid="trade-summary">
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 xl:grid-cols-8">
        <Figure
          label="Net result"
          value={fmtMoney(all.net)}
          cls={pnlColour(all.net)}
          sub={`gross ${fmtMoney(all.gross)} · cost ${fmtMoney(-all.cost)}`}
          help="Closed trades' net P&L, after costs"
          id="net"
        />
        <Figure
          label="Hit rate"
          value={pct(all.hitRate)}
          sub={`${String(all.wins)} won · ${String(all.losses)} lost`}
          help="Share of closed trades with a positive net"
          id="hit"
        />
        <Figure
          label="Profit factor"
          value={ratio(all.profitFactor)}
          cls={all.profitFactor == null ? '' : all.profitFactor >= 1 ? 'text-bull' : 'text-bear'}
          sub="won ÷ lost"
          help="Money won over money lost: above 1 makes money"
          id="pf"
        />
        <Figure
          label="Per trade"
          value={fmtMoney(all.expectancy)}
          cls={pnlColour(all.expectancy)}
          sub={`avg ${rText(all.avgR)}`}
          help="Expectancy: the average net of a closed trade, and in R (net over the money from fill to stop)"
          id="expectancy"
        />
        <Figure
          label="Avg win / loss"
          value={
            <>
              <span className="text-bull">{fmtMoney(all.avgWin)}</span>
              <span className="text-fg-muted"> / </span>
              <span className="text-bear">{fmtMoney(all.avgLoss)}</span>
            </>
          }
          sub={
            all.avgWin != null && all.avgLoss
              ? `win is ${(all.avgWin / -all.avgLoss).toFixed(1)}× loss`
              : ''
          }
          id="avg"
        />
        <Figure
          label="Best / worst"
          value={
            <>
              <span className={pnlColour(all.best?.net)}>{fmtMoney(all.best?.net)}</span>
              <span className="text-fg-muted"> / </span>
              <span className={pnlColour(all.worst?.net)}>{fmtMoney(all.worst?.net)}</span>
            </>
          }
          sub={all.best ? tradeName(all.best) : ''}
          help={
            all.best && all.worst
              ? `Best: ${tradeName(all.best)}. Worst: ${tradeName(all.worst)}.`
              : undefined
          }
          id="best"
        />
        <Figure
          label="Max drawdown"
          value={all.maxDrawdown > 0 ? fmtMoney(-all.maxDrawdown) : '₹0'}
          cls={all.maxDrawdown > 0 ? 'text-bear' : ''}
          sub={`worst run ${String(all.lossStreak)} loss${all.lossStreak === 1 ? '' : 'es'}`}
          help="The deepest fall of the running net from a peak, closed trades in exit order"
          id="drawdown"
        />
        <Figure
          label="Open now"
          value={all.open ? fmtMoney(all.unrealised) : '—'}
          cls={all.open ? pnlColour(all.unrealised) : 'text-fg-muted'}
          sub={`${String(all.open)} open, not in the figures`}
          help="Open trades' net so far at the price now"
          id="open"
        />
      </div>
      <Footnote s={all} />
      {scopes.length > 1 ? <Breakdown scopes={scopes} /> : null}
    </div>
  )
})

function Figure({
  label,
  value,
  sub,
  cls = '',
  help,
  id,
}: {
  label: string
  value: ReactNode
  sub?: string
  cls?: string
  help?: string | undefined
  id: string
}) {
  return (
    <div title={help} data-testid={`summary-${id}`} className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</div>
      <div className={`font-mono text-sm ${cls}`}>{value}</div>
      {sub ? <div className="truncate text-[10px] text-fg-muted">{sub}</div> : null}
    </div>
  )
}

function Footnote({ s }: { s: Summary }) {
  const reasons = (Object.keys(REASON_TEXT) as ExitReason[])
    .filter((r) => s.byReason[r])
    .map((r) => `${REASON_TEXT[r]} ${String(s.byReason[r])}`)
  const parts = [
    reasons.length ? `Exits: ${reasons.join(' · ')}` : 'No exits yet',
    s.avgHeldMs != null ? `avg held ${fmtDuration(s.avgHeldMs)}` : null,
  ].filter(Boolean)
  return (
    <div className="text-fg-muted" data-testid="summary-footnote">
      {parts.join(' · ')}
      {s.nonLive > 0 ? (
        <span className="ml-1 text-warn">
          · {s.nonLive} exit{s.nonLive === 1 ? '' : 's'} not on a live price
        </span>
      ) : null}
    </div>
  )
}

function Breakdown({ scopes }: { scopes: SummaryScope[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono whitespace-nowrap" data-testid="summary-breakdown">
        <thead className="text-fg-muted">
          <tr className="h-6 font-sans">
            <th className="text-left font-normal">By market</th>
            <th className="text-right font-normal">Trades</th>
            <th className="text-right font-normal">Won–lost</th>
            <th className="text-right font-normal">Hit</th>
            <th className="text-right font-normal">Net</th>
            <th className="text-right font-normal">Avg win</th>
            <th className="text-right font-normal">Avg loss</th>
            <th className="text-right font-normal" title="Money won over money lost">
              PF
            </th>
            <th className="text-right font-normal" title="Average net of a closed trade">
              Per trade
            </th>
            <th className="text-right font-normal">Avg R</th>
            <th className="text-right font-normal">Held</th>
            <th className="text-right font-normal">Open</th>
          </tr>
        </thead>
        <tbody>
          {scopes.map(({ key, label, total, summary: s }) => (
            <tr
              key={key}
              className={`h-6 ${total ? 'border-t border-border/60' : ''}`}
              data-testid={`summary-row-${key}`}
            >
              <td className={`font-sans ${total ? 'font-semibold' : 'pl-4 text-fg-muted'}`}>
                {label}
              </td>
              <td className="text-right">{s.closed}</td>
              <td className="text-right">
                {s.wins}–{s.losses}
              </td>
              <td className="text-right">{pct(s.hitRate)}</td>
              <td className={`text-right ${pnlColour(s.net)}`}>{fmtMoney(s.net)}</td>
              <td className="text-right text-bull">{fmtMoney(s.avgWin)}</td>
              <td className="text-right text-bear">{fmtMoney(s.avgLoss)}</td>
              <td className="text-right">{ratio(s.profitFactor)}</td>
              <td className={`text-right ${pnlColour(s.expectancy)}`}>{fmtMoney(s.expectancy)}</td>
              <td className="text-right">{rText(s.avgR)}</td>
              <td className="text-right text-fg-muted">{fmtDuration(s.avgHeldMs)}</td>
              <td className={`text-right ${s.open ? pnlColour(s.unrealised) : 'text-fg-muted'}`}>
                {s.open ? `${String(s.open)} · ${fmtMoney(s.unrealised)}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
