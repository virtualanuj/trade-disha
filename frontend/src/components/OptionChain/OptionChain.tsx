import { memo } from 'react'

import type { BuildUp, ChainOut, ChainRowOut, LegOut } from '../../api/types'
import { oiHeat } from '../../lib/chain'
import { fmtDate, fmtIstTime, fmtOi, fmtPrice, fmtSigned } from '../../lib/format'

const BUILDUP_LABEL: Record<BuildUp, string> = {
  long_buildup: 'Long build-up',
  short_buildup: 'Short build-up',
  short_covering: 'Short covering',
  long_unwinding: 'Long unwinding',
  none: '',
}

function heatStyle(leg: LegOut, maxAbs: number): React.CSSProperties {
  const h = oiHeat(leg.oi_chg_open, maxAbs)
  if (h === 0) return {}
  const colour = (leg.oi_chg_open ?? 0) > 0 ? 'var(--bull)' : 'var(--bear)'
  return { background: `color-mix(in srgb, ${colour} ${String(Math.round(h * 28))}%, transparent)` }
}

/** opens the ticket for a trade by hand on one leg (E23) */
type OnTrade = (strike: number, side: 'ce' | 'pe') => void

function Leg({
  leg,
  side,
  strike,
  maxAbs,
  onTrade,
}: {
  leg: LegOut
  side: 'ce' | 'pe'
  strike: number
  maxAbs: number
  onTrade: OnTrade | undefined
}) {
  const title = BUILDUP_LABEL[leg.buildup]
  const chgCls =
    leg.chg_pct == null ? '' : leg.chg_pct > 0 ? 'text-bull' : leg.chg_pct < 0 ? 'text-bear' : ''
  const oiCell = (
    <td className="px-1 text-right" style={heatStyle(leg, maxAbs)} title={title}>
      {fmtOi(leg.oi)}
    </td>
  )
  const dOiCell = (
    <td className="px-1 text-right text-fg-muted" style={heatStyle(leg, maxAbs)} title={title}>
      {leg.oi_chg_open == null ? '—' : fmtOi(leg.oi_chg_open)}
    </td>
  )
  const ivCell = <td className="px-1 text-right text-fg-muted">{leg.iv?.toFixed(1) ?? '—'}</td>
  const ltpCell = (
    <td className="px-1 text-right">
      {onTrade ? (
        <button
          type="button"
          className="w-full rounded px-0.5 text-right hover:bg-accent/20 hover:text-accent focus-visible:bg-accent/20"
          title={`Paper trade ${String(strike)} ${side.toUpperCase()}`}
          aria-label={`Paper trade ${String(strike)} ${side.toUpperCase()}`}
          onClick={() => {
            onTrade(strike, side)
          }}
        >
          {fmtPrice(leg.ltp)}
        </button>
      ) : (
        fmtPrice(leg.ltp)
      )}
    </td>
  )
  const chgCell = <td className={`px-1 text-right ${chgCls}`}>{fmtSigned(leg.chg_pct)}</td>
  return side === 'ce' ? (
    <>
      {oiCell}
      {dOiCell}
      {ivCell}
      {ltpCell}
      {chgCell}
    </>
  ) : (
    <>
      {chgCell}
      {ltpCell}
      {ivCell}
      {dOiCell}
      {oiCell}
    </>
  )
}

const Row = memo(function Row({
  row,
  atm,
  maxAbs,
  onTrade,
}: {
  row: ChainRowOut
  atm: number
  maxAbs: number
  onTrade: OnTrade | undefined
}) {
  const isAtm = row.strike === atm
  return (
    <tr
      className={`h-7 border-b border-border/60 font-mono ${isAtm ? 'bg-accent/15 font-semibold' : 'odd:bg-bg-row/40'}`}
      data-testid={isAtm ? 'atm-row' : undefined}
    >
      <Leg leg={row.ce} side="ce" strike={row.strike} maxAbs={maxAbs} onTrade={onTrade} />
      <td className="px-2 text-center font-sans font-semibold">{row.strike}</td>
      <Leg leg={row.pe} side="pe" strike={row.strike} maxAbs={maxAbs} onTrade={onTrade} />
    </tr>
  )
})

/**
 * The option chain. With `onTrade`, each LTP is a button that opens a paper-trade ticket
 * for that strike and side (E23); it must be stable, so the memoised rows do not redraw.
 */
export function OptionChain({
  chain,
  onTrade,
}: {
  chain: ChainOut | undefined
  onTrade?: OnTrade
}) {
  if (!chain) {
    return <p className="text-fg-muted">Waiting for option chain…</p>
  }
  return (
    <div className="flex h-full flex-col text-xs">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-semibold">
          {chain.index} <span className="font-normal text-fg-muted">{fmtDate(chain.expiry)}</span>
        </span>
        <span className="font-mono text-fg-muted">
          {chain.updated_ts ? fmtIstTime(chain.updated_ts) : '—'}
        </span>
      </div>
      <div className="mb-2 grid grid-cols-3 gap-2" data-testid="chain-summary">
        <Stat label="PCR" value={chain.pcr?.toFixed(2) ?? '—'} />
        <Stat label="Max pain" value={chain.max_pain != null ? String(chain.max_pain) : '—'} />
        <Stat label="ATM" value={String(chain.atm)} />
      </div>
      {chain.oi_baseline === 'partial' ? (
        <p className="mb-2 text-warn">OI change is measured from app start, not market open.</p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-bg-elev text-fg-muted">
            <tr className="h-7">
              <th className="px-1 text-right font-normal">OI</th>
              <th className="px-1 text-right font-normal">ΔOI</th>
              <th className="px-1 text-right font-normal">IV</th>
              <th className="px-1 text-right font-normal">LTP</th>
              <th className="px-1 text-right font-normal">chg%</th>
              <th className="px-2 text-center font-normal">Strike</th>
              <th className="px-1 text-right font-normal">chg%</th>
              <th className="px-1 text-right font-normal">LTP</th>
              <th className="px-1 text-right font-normal">IV</th>
              <th className="px-1 text-right font-normal">ΔOI</th>
              <th className="px-1 text-right font-normal">OI</th>
            </tr>
            <tr className="h-5 text-[10px] uppercase tracking-wide">
              <th colSpan={5} className="text-left font-normal text-bull">
                Calls · {fmtOi(chain.total_ce_oi)}
              </th>
              <th />
              <th colSpan={5} className="text-right font-normal text-bear">
                {fmtOi(chain.total_pe_oi)} · Puts
              </th>
            </tr>
          </thead>
          <tbody>
            {chain.rows.map((r) => (
              <Row
                key={r.strike}
                row={r}
                atm={chain.atm}
                maxAbs={chain.max_abs_oi_chg}
                onTrade={onTrade}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border bg-bg px-2 py-1">
      <div className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</div>
      <div className="font-mono text-sm">{value}</div>
    </div>
  )
}
