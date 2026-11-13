import { memo, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import type { IndexPrices, IndexStatsOut, ResolvedIndexOut } from '../../api/types'
import { fmtDate, fmtIstTime, fmtPrice, fmtSigned, pnlColour } from '../../lib/format'
import { usePref } from '../../lib/usePref'

const DETAILS_KEY = 'tradedisha.detailsOpen'
const asOpen = (v: unknown): boolean => v === true

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
      <span className={`font-mono text-lg transition-colors duration-150 ${cls}`}>
        {fmtPrice(value)}
      </span>
      <span className="font-mono text-xs text-fg-muted">{ts ? fmtIstTime(ts) : '—'}</span>
    </div>
  )
}

interface TileProps {
  meta: ResolvedIndexOut
  prices: IndexPrices | undefined
  stats: IndexStatsOut | undefined
}

const Tile = memo(function Tile({ meta, prices, stats }: TileProps) {
  const [open, setOpen] = usePref(DETAILS_KEY, asOpen)
  return (
    <div className="flex flex-col gap-3 rounded border border-border bg-bg-elev p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-base font-semibold">{meta.index}</span>
        <span className="text-xs text-fg-muted">
          exp {fmtDate(meta.options_expiry)}
          {meta.is_expiry_day ? <span className="ml-1 text-warn">(expiry day)</span> : null} · step{' '}
          {meta.strike_step} · lot {meta.lot_size}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Price label="Spot" value={prices?.spot_ltp ?? null} ts={prices?.spot_ts ?? null} />
        <Price
          label={`Fut ${meta.future.expiry ? fmtDate(meta.future.expiry) : ''}`}
          value={prices?.fut_ltp ?? null}
          ts={prices?.fut_ts ?? null}
        />
        <div className="flex min-w-0 flex-col">
          <span className="text-xs uppercase tracking-wide text-fg-muted">ATM</span>
          <span className="font-mono text-lg">{meta.atm}</span>
          <span className="truncate text-xs text-fg-muted">
            {meta.strikes.length} {meta.strikes.length === 1 ? 'strike' : 'strikes'}
          </span>
        </div>
      </div>
      <div>
        <button
          type="button"
          className="flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
          aria-expanded={open}
          onClick={() => {
            setOpen(!open)
          }}
        >
          <span aria-hidden="true" className="inline-block w-3">
            {open ? '▾' : '▸'}
          </span>
          Details
          {!open && stats?.change != null ? (
            <span className={`ml-2 font-mono ${pnlColour(stats.change)}`}>
              {fmtSigned(stats.change, 2)} ({fmtSigned(stats.change_pct, 2)}%)
            </span>
          ) : null}
        </button>
        {open ? <Details stats={stats} spot={prices?.spot_ltp ?? null} /> : null}
      </div>
    </div>
  )
})

/** How far `price` is from `ref`, as a signed percentage of `ref`. */
function distancePct(price: number | null, ref: number | null): string {
  if (price == null || !ref) return ''
  return `${fmtSigned(((price - ref) / ref) * 100, 1)}%`
}

function Details({ stats, spot }: { stats: IndexStatsOut | undefined; spot: number | null }) {
  const s = stats
  const pos52 =
    spot != null && s?.high_52w != null && s.low_52w != null && s.high_52w > s.low_52w
      ? (spot - s.low_52w) / (s.high_52w - s.low_52w)
      : null
  return (
    <div
      className="mt-3 grid gap-x-6 gap-y-3 border-t border-border pt-3 text-xs sm:grid-cols-2 xl:grid-cols-5"
      data-testid="index-details"
    >
      <Group title="Today">
        <Fact label="Open" value={fmtPrice(s?.day_open)} />
        <Fact label="High" value={fmtPrice(s?.day_high)} />
        <Fact label="Low" value={fmtPrice(s?.day_low)} />
        <RangeBar pos={s?.range_pos ?? null} label="Position in the day's range" />
      </Group>
      <Group title="52 weeks">
        <Fact
          label="High"
          value={fmtPrice(s?.high_52w)}
          sub={distancePct(spot, s?.high_52w ?? null)}
        />
        <Fact
          label="Low"
          value={fmtPrice(s?.low_52w)}
          sub={distancePct(spot, s?.low_52w ?? null)}
        />
        <RangeBar pos={pos52} label="Position in the 52-week range" />
      </Group>
      <Group title="Change on the day">
        <Fact label="Prev close" value={fmtPrice(s?.prev_close)} />
        <Fact
          label="Change"
          value={s?.change == null ? '—' : fmtSigned(s.change, 2)}
          sub={s?.change_pct == null ? '' : `${fmtSigned(s.change_pct, 2)}%`}
          cls={pnlColour(s?.change)}
        />
      </Group>
      <Group title="Futures">
        <Fact
          label="Premium over spot"
          value={s?.fut_premium == null ? '—' : fmtSigned(s.fut_premium, 2)}
        />
      </Group>
      <Group title="India VIX">
        <Fact
          label="VIX"
          value={s?.vix == null ? '—' : s.vix.toFixed(2)}
          sub={s?.vix_change_pct == null ? '' : `${fmtSigned(s.vix_change_pct, 2)}%`}
        />
      </Group>
    </div>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wide text-fg-muted">{title}</div>
      {children}
    </div>
  )
}

function Fact({
  label,
  value,
  sub = '',
  cls = '',
}: {
  label: string
  value: string
  sub?: string
  cls?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-fg-muted">{label}</span>
      <span className={`font-mono ${cls}`}>
        {value}
        {sub ? <span className="ml-1 text-[10px] text-fg-muted">{sub}</span> : null}
      </span>
    </div>
  )
}

/** A thin bar with a marker: low on the left, high on the right. */
function RangeBar({ pos, label }: { pos: number | null; label: string }) {
  if (pos == null) return null
  const pct = Math.min(100, Math.max(0, pos * 100))
  return (
    <div
      className="relative mt-1 h-1 rounded bg-border"
      role="img"
      aria-label={`${label}: ${pct.toFixed(0)}%`}
      title={`${label}: ${pct.toFixed(0)}%`}
    >
      <div
        className="absolute -top-1 h-3 w-0.5 rounded bg-accent"
        style={{ left: `${pct.toFixed(1)}%` }}
      />
    </div>
  )
}

export function IndexTiles({
  instruments,
  prices,
  stats = {},
}: {
  instruments: ResolvedIndexOut[]
  prices: Record<string, IndexPrices>
  stats?: Record<string, IndexStatsOut>
}) {
  if (!instruments.length) {
    return <p className="text-fg-muted">Waiting for instruments…</p>
  }
  return (
    <div className={instruments.length > 1 ? 'grid gap-4 md:grid-cols-2' : 'grid gap-4'}>
      {instruments.map((m) => (
        <Tile key={m.index} meta={m} prices={prices[m.index]} stats={stats[m.index]} />
      ))}
    </div>
  )
}
