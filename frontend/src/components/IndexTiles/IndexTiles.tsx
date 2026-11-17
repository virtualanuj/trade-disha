import { memo } from 'react'
import type { ReactNode } from 'react'

import type { IndexPrices, IndexStatsOut, ResolvedIndexOut, SectorOut } from '../../api/types'
import { fmtDate, fmtPrice, fmtSigned, pnlColour } from '../../lib/format'
import { Fact, Group, Price, RangeBar } from '../Facts/Facts'
import { useFlash } from '../../lib/useFlash'
import { usePref } from '../../lib/usePref'

const DETAILS_KEY = 'tradedisha.detailsOpen'
const SECTORS_KEY = 'tradedisha.sectorsOpen'
/** Details start closed; sectors start open (they were asked for on show) */
const asOpen = (v: unknown): boolean => v === true
const asOpenByDefault = (v: unknown): boolean => v !== false

interface DisclosureProps {
  open: boolean
  onToggle: () => void
  label: string
  /** shown beside the label while closed */
  summary?: ReactNode
}

/** The chevron button that opens and closes a section of the panel. */
function Disclosure({ open, onToggle, label, summary }: DisclosureProps) {
  return (
    <button
      type="button"
      className="flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
      aria-expanded={open}
      onClick={onToggle}
    >
      <span aria-hidden="true" className="inline-block w-3">
        {open ? '▾' : '▸'}
      </span>
      {label}
      {!open && summary != null ? <span className="ml-2 font-mono">{summary}</span> : null}
    </button>
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
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="text-base font-semibold">{meta.index}</span>
        <span className="text-xs text-fg-muted">
          exp {fmtDate(meta.options_expiry)}
          {meta.is_expiry_day ? <span className="ml-1 text-warn">(expiry day)</span> : null} · step{' '}
          {meta.strike_step} · lot {meta.lot_size}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Price label="Spot" value={prices?.spot_ltp ?? null} ts={prices?.spot_ts ?? null} />
        <Price
          label={`Fut ${meta.future.expiry ? fmtDate(meta.future.expiry) : ''}`}
          value={prices?.fut_ltp ?? null}
          ts={prices?.fut_ts ?? null}
        />
      </div>
      {stats?.sectors.length ? <Sectors sectors={stats.sectors} /> : null}
      <div>
        <Disclosure
          open={open}
          onToggle={() => {
            setOpen(!open)
          }}
          label="Details"
          summary={
            stats?.change != null ? (
              <span className={pnlColour(stats.change)}>
                {fmtSigned(stats.change, 2)} ({fmtSigned(stats.change_pct, 2)}%)
              </span>
            ) : null
          }
        />
        {open ? <Details meta={meta} stats={stats} spot={prices?.spot_ltp ?? null} /> : null}
      </div>
    </div>
  )
})

function sectorTitle(s: SectorOut): string {
  if (s.prev_close == null) return s.name
  const pts = s.change == null ? '' : ` · ${fmtSigned(s.change, 2)}`
  return `${s.name} · prev close ${fmtPrice(s.prev_close)}${pts}`
}

function fmtChange(s: SectorOut): string {
  if (s.change == null || s.change_pct == null) return '—'
  return `${fmtSigned(s.change, 2)} (${fmtSigned(s.change_pct, 2)}%)`
}

/** One sector as a small box like spot and futures: name, value, change (% change). */
const SectorCard = memo(function SectorCard({ s }: { s: SectorOut }) {
  const flash = useFlash(s.ltp)
  const cls = flash === 'up' ? 'text-bull' : flash === 'down' ? 'text-bear' : 'text-fg'
  return (
    <div
      className="flex min-w-0 flex-col rounded border border-border/60 px-2 py-1.5"
      data-testid="sector"
      title={sectorTitle(s)}
    >
      <span className="truncate text-xs font-semibold text-fg">{s.label}</span>
      <span className={`font-mono text-sm transition-colors duration-150 ${cls}`}>
        {fmtPrice(s.ltp)}
      </span>
      <span className={`truncate font-mono text-[11px] ${pnlColour(s.change)}`}>
        {fmtChange(s)}
      </span>
    </div>
  )
})

/** How many sectors are up and down on the day: the line shown while they are closed. */
function Breadth({ sectors }: { sectors: SectorOut[] }) {
  const up = sectors.filter((s) => (s.change ?? 0) > 0).length
  const down = sectors.filter((s) => (s.change ?? 0) < 0).length
  return (
    <>
      <span className="text-bull">{up} up</span>
      {' · '}
      <span className="text-bear">{down} down</span>
    </>
  )
}

/**
 * The sector indices behind this index (E11): a box per sector, in config order, with the
 * change green up and red down like the index's own. Opens and closes like Details, open
 * by default, remembered. Display only.
 */
function Sectors({ sectors }: { sectors: SectorOut[] }) {
  const [open, setOpen] = usePref(SECTORS_KEY, asOpenByDefault)
  return (
    <div className="border-t border-border pt-3" data-testid="index-sectors">
      <Disclosure
        open={open}
        onToggle={() => {
          setOpen(!open)
        }}
        label="Sectors"
        summary={<Breadth sectors={sectors} />}
      />
      {open ? (
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
          {sectors.map((s) => (
            <SectorCard key={s.name} s={s} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

/** How far `price` is from `ref`, as a signed percentage of `ref`. */
function distancePct(price: number | null, ref: number | null): string {
  if (price == null || !ref) return ''
  return `${fmtSigned(((price - ref) / ref) * 100, 1)}%`
}

interface DetailsProps {
  meta: ResolvedIndexOut
  stats: IndexStatsOut | undefined
  spot: number | null
}

function Details({ meta, stats, spot }: DetailsProps) {
  const s = stats
  const pos52 =
    spot != null && s?.high_52w != null && s.low_52w != null && s.high_52w > s.low_52w
      ? (spot - s.low_52w) / (s.high_52w - s.low_52w)
      : null
  return (
    <div
      className="mt-3 grid gap-x-6 gap-y-3 border-t border-border pt-3 text-xs sm:grid-cols-2 xl:grid-cols-6"
      data-testid="index-details"
    >
      <Group title="Options">
        <Fact label="ATM" value={String(meta.atm)} />
        <Fact label="Strikes" value={String(meta.strikes.length)} />
      </Group>
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
