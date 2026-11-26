import { memo } from 'react'

import { fmtPrice, fmtSigned } from '../../lib/format'
import type { Rate } from '../../lib/rates'

/** Green up, red down, muted flat or unknown: by sign, since a small % still has a side. */
function changeColour(v: number | null): string {
  if (v == null || v === 0) return 'text-fg-muted'
  return v > 0 ? 'text-bull' : 'text-bear'
}

/**
 * The rates strip under the top bar (E22, spec §13.2): NIFTY, SENSEX, the metals and
 * their ETFs, each with its price and day change %. An entry with a tab opens it.
 */
export function RatesStrip({
  rates,
  onOpen,
}: {
  rates: Rate[]
  /** stable: the tab to show and, on BULLION, the metal to focus */
  onOpen: (tab: string, metal: string | null) => void
}) {
  return (
    <div
      className="flex items-center gap-x-1 overflow-x-auto whitespace-nowrap border-b border-border bg-bg-elev px-3 py-1 text-xs"
      role="list"
      aria-label="Rates"
      data-testid="rates-strip"
    >
      {rates.map((r, i) => (
        <span key={r.name} role="listitem" className="flex items-center">
          {i > 0 ? (
            <span aria-hidden="true" className="px-2 text-border">
              │
            </span>
          ) : null}
          <RateEntry r={r} onOpen={onOpen} />
        </span>
      ))}
    </div>
  )
}

const RateEntry = memo(function RateEntry({
  r,
  onOpen,
}: {
  r: Rate
  onOpen: (tab: string, metal: string | null) => void
}) {
  const body = (
    <>
      <span className="font-medium text-fg-muted">{r.name}</span>
      <span className="font-mono tabular-nums text-fg">{fmtPrice(r.ltp)}</span>
      <span className={`font-mono tabular-nums ${changeColour(r.changePct)}`}>
        {r.changePct == null ? '' : `${fmtSigned(r.changePct, 2)}%`}
      </span>
    </>
  )
  const { tab } = r
  if (tab == null) {
    return (
      <span className="flex items-baseline gap-1.5" data-testid={`rate-${r.name}`}>
        {body}
      </span>
    )
  }
  return (
    <button
      type="button"
      className="flex items-baseline gap-1.5 rounded px-1 hover:bg-accent/10"
      data-testid={`rate-${r.name}`}
      title={r.metal ? `Open BULLION on ${r.metal}` : `Open ${tab}`}
      onClick={() => {
        onOpen(tab, r.metal)
      }}
    >
      {body}
    </button>
  )
})
