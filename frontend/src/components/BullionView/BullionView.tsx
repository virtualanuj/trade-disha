import { memo, useCallback } from 'react'
import type { ReactNode } from 'react'

import type {
  BullionEtfOut,
  BullionMetalOut,
  BullionOut,
  MarketStatus,
  TicketTarget,
} from '../../api/types'
import { fmtCount, fmtDate, fmtOi, fmtPrice, fmtSigned, pnlColour } from '../../lib/format'
import { usePref } from '../../lib/usePref'
import { Fact, Group, Price, RangeBar } from '../Facts/Facts'

/** MCX quotes gold per 10 g and silver per kg. */
const UNIT: Record<string, string> = { GOLD: '₹ / 10 g', SILVER: '₹ / kg' }
const EMPTY: never[] = []
/** an ETF's note while NSE is not trading (MCX trades on, so it is not an outage) */
const NSE_NOTE: Record<MarketStatus, string> = {
  pre_open: 'NSE pre-open',
  live: '',
  closed: 'NSE closed',
  holiday: 'NSE holiday',
}
/** each card's Details open or closed, remembered apart (E31): `<key>.GOLD`, `<key>.GOLDBEES` */
const DETAILS_KEY = 'tradedisha.bullionDetailsOpen'
const asOpen = (v: unknown): boolean => v === true

/**
 * An MCX tab's tiles (E32): its contract's future, then the gold/silver ratio (spec §6.6,
 * §13.2). GOLDM and SILVERM are tabs of their own (E29). With `metal`, only that contract;
 * left out, every contract. With `onTrade` (stable), each card has Buy and Sell for a
 * paper trade by hand (E23).
 */
export function BullionCards({
  bullion,
  metal,
  onTrade,
}: {
  bullion: BullionOut | null
  /** the metal tab; left out, every metal side by side */
  metal?: string
  onTrade?: (t: TicketTarget) => void
}) {
  const all = bullion?.metals ?? EMPTY
  const focused = metal === undefined ? undefined : all.find((m) => m.metal === metal)
  const metals = focused ? [focused] : all
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
            <MetalCard m={m} onTrade={onTrade} />
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

/**
 * NSE's BULLION tab (E32): the gold and silver ETFs (E25) side by side, each with its own
 * Details. Display only. `nseStatus` notes when NSE is not trading.
 */
export function EtfCards({
  etfs,
  nseStatus = null,
}: {
  etfs: BullionEtfOut[]
  nseStatus?: MarketStatus | null
}) {
  if (etfs.length === 0) {
    return (
      <p className="text-xs text-fg-muted">
        Live feed only: GOLDBEES and SILVERBEES come from NSE through Upstox.
      </p>
    )
  }
  const note = nseStatus ? NSE_NOTE[nseStatus] : ''
  return (
    <div className="grid gap-3 lg:grid-cols-2" data-testid="etf-view">
      {etfs.map((e) => (
        <Box key={e.symbol}>
          <EtfCard e={e} note={note} />
        </Box>
      ))}
    </div>
  )
}

function Box({ children }: { children: ReactNode }) {
  return <section className="rounded border border-border bg-bg-elev p-3">{children}</section>
}

function withQty(price: number | null, qty: number | null): string {
  return qty == null ? fmtPrice(price) : `${fmtPrice(price)} × ${fmtCount(qty)}`
}

/** Where `ltp` sits between `low` and `high`, 0 to 1; null when unknown or flat. */
function rangePos(ltp: number | null, high: number | null, low: number | null): number | null {
  return ltp != null && high != null && low != null && high > low
    ? (ltp - low) / (high - low)
    : null
}

/** `ref` as a signed percentage away from `price`. */
function awayPct(price: number | null, ref: number | null): string {
  if (price == null || !ref) return ''
  return `${fmtSigned(((ref - price) / price) * 100, 1)}%`
}

/**
 * One contract's future: GOLD, GOLDM, SILVER or SILVERM, each a market of its own (E29).
 * A mini is quoted like its metal (per 10 g, per kg) and trades as itself.
 */
const MetalCard = memo(function MetalCard({
  m,
  onTrade,
}: {
  m: BullionMetalOut
  onTrade: ((t: TicketTarget) => void) | undefined
}) {
  const [open, onToggle] = useDetails(m.metal)
  const yearPos = rangePos(m.ltp, m.range_high, m.range_low)
  const metal = m.metal.startsWith('SILVER') ? 'SILVER' : 'GOLD'
  return (
    <div className="flex flex-col gap-3" data-testid={`bullion-${m.metal}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base font-semibold">{m.metal}</span>
        <span className="truncate text-xs text-fg-muted">
          {m.trading_symbol} · exp {fmtDate(m.expiry)} · lot {m.lot_size}
          {m.point_value ? ` · ₹${String(m.point_value)} / point` : ''}
        </span>
      </div>
      <div className="flex items-end gap-4">
        <Price label={`LTP ${UNIT[metal] ?? '₹'}`} value={m.ltp} ts={m.updated_ts} />
        <span className={`pb-5 font-mono text-sm ${pnlColour(m.change)}`}>
          {m.change == null ? '—' : fmtSigned(m.change, 2)}
          {m.change_pct == null ? '' : ` (${fmtSigned(m.change_pct, 2)}%)`}
        </span>
        {onTrade ? <TradeButtons contract={m.metal} onTrade={onTrade} /> : null}
      </div>
      <DetailsToggle open={open} onToggle={onToggle} />
      {open ? <MetalDetails m={m} yearPos={yearPos} /> : null}
    </div>
  )
})

/** Buy and Sell for a paper trade by hand in one contract, which is its own market. */
function TradeButtons({
  contract,
  onTrade,
}: {
  contract: string
  onTrade: (t: TicketTarget) => void
}) {
  return (
    <span className="ml-auto flex gap-1 pb-5 text-xs" role="group" aria-label="Paper trade">
      <button
        type="button"
        className="rounded border border-bull/60 px-2 py-0.5 font-medium text-bull hover:bg-bull/10"
        title={`Paper trade: buy the ${contract} future`}
        onClick={() => {
          onTrade({ index: contract, direction: 'BUY_FUT', strike: null })
        }}
      >
        Buy
      </button>
      <button
        type="button"
        className="rounded border border-bear/60 px-2 py-0.5 font-medium text-bear hover:bg-bear/10"
        title={`Paper trade: sell the ${contract} future`}
        onClick={() => {
          onTrade({ index: contract, direction: 'SELL_FUT', strike: null })
        }}
      >
        Sell
      </button>
    </span>
  )
}

/** One card's Details, open or closed: only the card clicked changes (E31). */
function useDetails(card: string): [boolean, () => void] {
  const [open, setOpen] = usePref(`${DETAILS_KEY}.${card}`, asOpen)
  const toggle = useCallback(() => {
    setOpen(!open)
  }, [open, setOpen])
  return [open, toggle]
}

function DetailsToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
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
  )
}

/** GOLDBEES / SILVERBEES: the NSE ETF's own quote, under its metal (E25). No trading. */
const EtfCard = memo(function EtfCard({
  e,
  note,
}: {
  e: BullionEtfOut
  /** why it is not ticking: NSE closed, a holiday, pre-open; empty while NSE trades */
  note: string
}) {
  const [open, onToggle] = useDetails(e.symbol)
  return (
    <div className="flex flex-col gap-3" data-testid={`etf-${e.symbol}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base font-semibold">{e.symbol}</span>
        <span className="truncate text-xs text-fg-muted">NSE ETF</span>
      </div>
      <div className="flex items-end gap-4">
        <Price label="LTP ₹ / unit" value={e.ltp} ts={e.updated_ts} />
        <span className={`pb-5 font-mono text-sm ${pnlColour(e.change)}`}>
          {e.change == null ? '—' : fmtSigned(e.change, 2)}
          {e.change_pct == null ? '' : ` (${fmtSigned(e.change_pct, 2)}%)`}
        </span>
        {note ? <span className="ml-auto pb-5 text-xs text-fg-muted">{note}</span> : null}
      </div>
      <DetailsToggle open={open} onToggle={onToggle} />
      {open ? <EtfDetails e={e} /> : null}
    </div>
  )
})

/** The ETF's day, liquidity and 52-week figures, shown when opened. */
function EtfDetails({ e }: { e: BullionEtfOut }) {
  return (
    <div
      className="grid gap-x-6 gap-y-3 border-t border-border pt-3 text-xs sm:grid-cols-2"
      data-testid={`etf-details-${e.symbol}`}
    >
      <Group title="Today">
        <Fact label="Open" value={fmtPrice(e.day_open)} />
        <Fact label="High" value={fmtPrice(e.day_high)} />
        <Fact label="Low" value={fmtPrice(e.day_low)} />
        <RangeBar pos={e.range_pos} label="Position in the day's range" />
        <Fact label="Prev close" value={fmtPrice(e.prev_close)} />
        <Fact label="ATP (VWAP)" value={fmtPrice(e.atp)} />
      </Group>
      <Group title="Liquidity">
        <Fact label="Volume" value={fmtCount(e.volume)} />
        <Fact label="Bid" value={withQty(e.bid, e.bid_qty)} />
        <Fact label="Ask" value={withQty(e.ask, e.ask_qty)} />
        <Fact label="Spread" value={e.spread == null ? '—' : e.spread.toFixed(2)} />
      </Group>
      <Group title="52 weeks">
        <Fact label="High" value={fmtPrice(e.range_high)} sub={awayPct(e.ltp, e.range_high)} />
        <Fact label="Low" value={fmtPrice(e.range_low)} sub={awayPct(e.ltp, e.range_low)} />
        <RangeBar
          pos={rangePos(e.ltp, e.range_high, e.range_low)}
          label="Position in the 52-week range"
        />
      </Group>
    </div>
  )
}

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
