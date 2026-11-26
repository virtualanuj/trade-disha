import { memo, useCallback } from 'react'
import type { ReactNode } from 'react'

import type { BullionMetalOut, BullionOut, TicketTarget } from '../../api/types'
import { fmtCount, fmtDate, fmtOi, fmtPrice, fmtSigned, pnlColour } from '../../lib/format'
import { usePref } from '../../lib/usePref'
import { Fact, Group, Price, RangeBar } from '../Facts/Facts'

/** MCX quotes gold per 10 g and silver per kg. */
const UNIT: Record<string, string> = { GOLD: '₹ / 10 g', SILVER: '₹ / kg' }
const EMPTY: never[] = []
/** one remembered choice for both metal cards, apart from the index details' */
const DETAILS_KEY = 'tradedisha.bullionDetailsOpen'
const asOpen = (v: unknown): boolean => v === true

/** Picks the metal every BULLION panel shows: market view, signal, chart, evidence, trades. */
export function MetalSwitch({
  names,
  metal,
  onSelect,
}: {
  names: string[]
  metal: string
  onSelect: (metal: string) => void
}) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Metal">
      {names.map((n) => (
        <button
          key={n}
          type="button"
          aria-pressed={n === metal}
          onClick={() => {
            onSelect(n)
          }}
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            n === metal ? 'bg-accent/20 text-fg' : 'text-fg-muted hover:text-fg'
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  )
}

/**
 * The BULLION tab's tiles: a card per metal and the gold/silver ratio (spec §6.6, §13.2).
 * With `onTrade` (stable), each card has Buy and Sell for a paper trade by hand (E23).
 */
export function BullionCards({
  bullion,
  onTrade,
}: {
  bullion: BullionOut | null
  onTrade?: (t: TicketTarget) => void
}) {
  const metals = bullion?.metals ?? EMPTY
  // one choice for both cards, like the index details: opening one opens both
  const [open, setOpen] = usePref(DETAILS_KEY, asOpen)
  const toggle = useCallback(() => {
    setOpen(!open)
  }, [open, setOpen])
  if (metals.length === 0) {
    return (
      <p className="text-xs text-fg-muted">
        Live feed only: gold and silver come from MCX through Upstox.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-3" data-testid="bullion-view">
      <div className="grid gap-3 lg:grid-cols-2">
        {metals.map((m) => (
          <Box key={m.metal}>
            <MetalCard m={m} open={open} onToggle={toggle} onTrade={onTrade} />
          </Box>
        ))}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-xs">
        <span
          className="text-fg-muted"
          title="Kilograms of silver one kilogram of gold buys, from the two near-month futures"
        >
          Gold / silver ratio
        </span>
        <span className="font-mono text-base" data-testid="bullion-ratio">
          {bullion?.ratio == null ? '—' : bullion.ratio.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

function Box({ children }: { children: ReactNode }) {
  return <section className="rounded border border-border bg-bg-elev p-3">{children}</section>
}

function withQty(price: number | null, qty: number | null): string {
  return qty == null ? fmtPrice(price) : `${fmtPrice(price)} × ${fmtCount(qty)}`
}

/** `ref` as a signed percentage away from `price`. */
function awayPct(price: number | null, ref: number | null): string {
  if (price == null || !ref) return ''
  return `${fmtSigned(((ref - price) / price) * 100, 1)}%`
}

const MetalCard = memo(function MetalCard({
  m,
  open,
  onToggle,
  onTrade,
}: {
  m: BullionMetalOut
  open: boolean
  onToggle: () => void
  onTrade: ((t: TicketTarget) => void) | undefined
}) {
  const yearPos =
    m.ltp != null && m.range_high != null && m.range_low != null && m.range_high > m.range_low
      ? (m.ltp - m.range_low) / (m.range_high - m.range_low)
      : null
  return (
    <div className="flex flex-col gap-3" data-testid={`bullion-${m.metal}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base font-semibold">{m.metal}</span>
        <span className="truncate text-xs text-fg-muted">
          {m.trading_symbol} · exp {fmtDate(m.expiry)} · lot {m.lot_size}
        </span>
      </div>
      <div className="flex items-end gap-4">
        <Price label={`LTP ${UNIT[m.metal] ?? '₹'}`} value={m.ltp} ts={m.updated_ts} />
        <span className={`pb-5 font-mono text-sm ${pnlColour(m.change)}`}>
          {m.change == null ? '—' : fmtSigned(m.change, 2)}
          {m.change_pct == null ? '' : ` (${fmtSigned(m.change_pct, 2)}%)`}
        </span>
        {onTrade ? (
          <span className="ml-auto flex gap-1 pb-5 text-xs" role="group" aria-label="Paper trade">
            <button
              type="button"
              className="rounded border border-bull/60 px-2 py-0.5 font-medium text-bull hover:bg-bull/10"
              title={`Paper trade: buy the ${m.metal} future`}
              onClick={() => {
                onTrade({ index: m.metal, direction: 'BUY_FUT', strike: null })
              }}
            >
              Buy
            </button>
            <button
              type="button"
              className="rounded border border-bear/60 px-2 py-0.5 font-medium text-bear hover:bg-bear/10"
              title={`Paper trade: sell the ${m.metal} future`}
              onClick={() => {
                onTrade({ index: m.metal, direction: 'SELL_FUT', strike: null })
              }}
            >
              Sell
            </button>
          </span>
        ) : null}
      </div>
      <button
        type="button"
        className="flex items-center gap-1 self-start text-xs text-fg-muted hover:text-fg"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span aria-hidden="true" className="inline-block w-3">
          {open ? '▾' : '▸'}
        </span>
        Details
      </button>
      {open ? <MetalDetails m={m} yearPos={yearPos} /> : null}
    </div>
  )
})

/** The day, liquidity, contract-range and next-month figures, shown when opened. */
function MetalDetails({ m, yearPos }: { m: BullionMetalOut; yearPos: number | null }) {
  return (
    <div
      className="grid gap-x-6 gap-y-3 border-t border-border pt-3 text-xs sm:grid-cols-2"
      data-testid={`bullion-details-${m.metal}`}
    >
      <Group title="Today">
        <Fact label="Open" value={fmtPrice(m.day_open)} />
        <Fact label="High" value={fmtPrice(m.day_high)} />
        <Fact label="Low" value={fmtPrice(m.day_low)} />
        <RangeBar pos={m.range_pos} label="Position in the day's range" />
        <Fact label="Prev close" value={fmtPrice(m.prev_close)} />
        <Fact label="ATP (VWAP)" value={fmtPrice(m.atp)} />
      </Group>
      <Group title="Liquidity">
        <Fact label="Volume" value={fmtCount(m.volume)} />
        <Fact label="Open interest" value={fmtOi(m.oi)} />
        <Fact label="Bid" value={withQty(m.bid, m.bid_qty)} />
        <Fact label="Ask" value={withQty(m.ask, m.ask_qty)} />
        <Fact label="Spread" value={m.spread == null ? '—' : m.spread.toFixed(2)} />
        <Fact
          label="Buy / sell qty"
          value={`${fmtCount(m.tbq)} / ${fmtCount(m.tsq)}`}
          sub={m.buy_sell_ratio == null ? '' : `${m.buy_sell_ratio.toFixed(2)}×`}
          cls={m.buy_sell_ratio == null ? '' : pnlColour(m.buy_sell_ratio - 1)}
        />
      </Group>
      <Group title="Contract, 1 year">
        <Fact label="High" value={fmtPrice(m.range_high)} sub={awayPct(m.ltp, m.range_high)} />
        <Fact label="Low" value={fmtPrice(m.range_low)} sub={awayPct(m.ltp, m.range_low)} />
        <RangeBar pos={yearPos} label="Position in the year's range" />
        <Fact label="Upper circuit" value={fmtPrice(m.upper_circuit)} />
        <Fact label="Lower circuit" value={fmtPrice(m.lower_circuit)} />
      </Group>
      <Group title="Next month">
        <Fact
          label={m.next_expiry ? `Exp ${fmtDate(m.next_expiry)}` : 'Contract'}
          value={fmtPrice(m.next_ltp)}
        />
        <Fact
          label="Spread over near"
          value={m.calendar_spread == null ? '—' : fmtSigned(m.calendar_spread, 2)}
          sub={m.calendar_spread_pct == null ? '' : `${fmtSigned(m.calendar_spread_pct, 2)}%`}
        />
      </Group>
    </div>
  )
}
