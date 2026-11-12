import { memo, useEffect, useRef, useState } from 'react'

import type { IndexPrices, ResolvedIndexOut } from '../../api/types'
import { fmtIstTime, fmtPrice } from '../../lib/format'

function useFlash(value: number | null): 'up' | 'down' | null {
  const prev = useRef<number | null>(null)
  const [dir, setDir] = useState<'up' | 'down' | null>(null)
  useEffect(() => {
    const p = prev.current
    prev.current = value
    if (value == null || p == null || value === p) return
    setDir(value > p ? 'up' : 'down')
    const id = setTimeout(() => {
      setDir(null)
    }, 150)
    return () => {
      clearTimeout(id)
    }
  }, [value])
  return dir
}

function Price({ label, value, ts }: { label: string; value: number | null; ts: number | null }) {
  const flash = useFlash(value)
  const cls = flash === 'up' ? 'text-bull' : flash === 'down' ? 'text-bear' : 'text-fg'
  return (
    <div className="flex min-w-0 flex-col">
      <span className="truncate text-xs uppercase tracking-wide text-fg-muted">{label}</span>
      <span className={`font-mono text-xl transition-colors duration-150 ${cls}`}>
        {fmtPrice(value)}
      </span>
      <span className="font-mono text-xs text-fg-muted">{ts ? fmtIstTime(ts) : '—'}</span>
    </div>
  )
}

interface TileProps {
  meta: ResolvedIndexOut
  prices: IndexPrices | undefined
}

const Tile = memo(function Tile({ meta, prices }: TileProps) {
  return (
    <div className="flex flex-col gap-3 rounded border border-border bg-bg-elev p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-base font-semibold">{meta.index}</span>
        <span className="text-xs text-fg-muted">
          exp {meta.options_expiry}
          {meta.is_expiry_day ? <span className="ml-1 text-warn">(expiry day)</span> : null} · step{' '}
          {meta.strike_step} · lot {meta.lot_size}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Price label="Spot" value={prices?.spot_ltp ?? null} ts={prices?.spot_ts ?? null} />
        <Price
          label={`Fut ${meta.future.expiry ?? ''}`}
          value={prices?.fut_ltp ?? null}
          ts={prices?.fut_ts ?? null}
        />
        <div className="flex min-w-0 flex-col">
          <span className="text-xs uppercase tracking-wide text-fg-muted">ATM</span>
          <span className="font-mono text-xl">{meta.atm}</span>
          <span className="truncate text-xs text-fg-muted">{meta.strikes.length} strikes</span>
        </div>
      </div>
    </div>
  )
})

export function IndexTiles({
  instruments,
  prices,
}: {
  instruments: ResolvedIndexOut[]
  prices: Record<string, IndexPrices>
}) {
  if (!instruments.length) {
    return <p className="text-fg-muted">Waiting for instruments…</p>
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {instruments.map((m) => (
        <Tile key={m.index} meta={m} prices={prices[m.index]} />
      ))}
    </div>
  )
}
