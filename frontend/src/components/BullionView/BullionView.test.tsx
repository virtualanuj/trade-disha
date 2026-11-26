import { fireEvent, render, renderHook, screen } from '@testing-library/react'
import { act } from 'react'

import type { BullionMetalOut, BullionOut } from '../../api/types'
import { useBullionMetal } from '../../lib/useBullionMetal'
import { BullionCards, MetalSwitch } from './BullionView'

const gold: BullionMetalOut = {
  metal: 'GOLD',
  trading_symbol: 'GOLD FUT 04 DEC 26',
  expiry: '2026-12-04',
  lot_size: 1,
  ltp: 134914,
  prev_close: 136705,
  change: -1791,
  change_pct: -1.31,
  day_open: 135853,
  day_high: 136055,
  day_low: 134385,
  range_pos: 0.32,
  atp: 135142.9,
  volume: 5040,
  oi: 15627,
  bid: 134900,
  ask: 134920,
  bid_qty: 3,
  ask_qty: 5,
  spread: 20,
  tbq: 237,
  tsq: 153,
  buy_sell_ratio: 1.55,
  range_high: 140000,
  range_low: 90000,
  lower_circuit: 132604,
  upper_circuit: 140806,
  next_symbol: 'GOLD FUT 05 FEB 27',
  next_expiry: '2027-02-05',
  next_ltp: 136939,
  calendar_spread: 2025,
  calendar_spread_pct: 1.5,
  updated_ts: 1_794_820_957_000,
}
const silver: BullionMetalOut = { ...gold, metal: 'SILVER', trading_symbol: 'SILVER FUT 04 DEC 26' }
const bullion: BullionOut = { metals: [gold, silver], ratio: 79.31 }
function show(b: BullionOut | null = bullion) {
  return render(<BullionCards bullion={b} />)
}

describe('BullionCards', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('keeps the details closed at first, with the price and change on show', () => {
    show()
    const g = screen.getByTestId('bullion-GOLD')
    expect(g).toHaveTextContent('1,34,914.00')
    expect(g).toHaveTextContent('-1791.00 (-1.31%)')
    expect(screen.queryByTestId('bullion-details-GOLD')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Details/ })).toHaveLength(2)
  })

  it('opens the details of both metals together, and remembers it', () => {
    show()
    const [goldToggle] = screen.getAllByRole('button', { name: /Details/ })
    expect(goldToggle).toHaveAttribute('aria-expanded', 'false')
    if (goldToggle) fireEvent.click(goldToggle)
    expect(screen.getByTestId('bullion-details-GOLD')).toHaveTextContent('ATP (VWAP)')
    expect(screen.getByTestId('bullion-details-SILVER')).toBeInTheDocument()
    expect(localStorage.getItem('tradedisha.bullionDetailsOpen')).toBe('true')
    expect(localStorage.getItem('tradedisha.detailsOpen')).toBeNull() // the index one is apart
  })

  it('shows each metal with its day, liquidity, contract and next-month figures', () => {
    localStorage.setItem('tradedisha.bullionDetailsOpen', 'true')
    show()
    const g = screen.getByTestId('bullion-GOLD')
    expect(g).toHaveTextContent('GOLD FUT 04 DEC 26 · exp 04/12/2026 · lot 1')
    expect(g).toHaveTextContent('LTP ₹ / 10 g')
    expect(g).toHaveTextContent('1,34,914.00')
    expect(g).toHaveTextContent('-1791.00 (-1.31%)')
    expect(g).toHaveTextContent('ATP (VWAP)1,35,142.90')
    expect(g).toHaveTextContent('Bid1,34,900.00 × 3')
    expect(g).toHaveTextContent('Buy / sell qty237 / 1531.55×')
    expect(g).toHaveTextContent('Upper circuit1,40,806.00')
    expect(g).toHaveTextContent('Exp 05/02/20271,36,939.00')
    expect(g).toHaveTextContent('Spread over near+2025.00+1.50%')
    expect(screen.getByTestId('bullion-SILVER')).toHaveTextContent('LTP ₹ / kg')
    expect(screen.getByTestId('bullion-ratio')).toHaveTextContent('79.31')
  })

  it('shows dashes for what Upstox has not sent', () => {
    const empty: BullionMetalOut = {
      ...gold,
      ltp: null,
      change: null,
      change_pct: null,
      next_ltp: null,
      calendar_spread: null,
      calendar_spread_pct: null,
      updated_ts: null,
    }
    localStorage.setItem('tradedisha.bullionDetailsOpen', 'true')
    show({ metals: [empty], ratio: null })
    expect(screen.getByTestId('bullion-ratio')).toHaveTextContent('—')
    expect(screen.getByTestId('bullion-GOLD')).toHaveTextContent('Spread over near—')
  })

  it('explains that bullion needs the live feed', () => {
    show({ metals: [], ratio: null })
    expect(screen.getByText(/Live feed only/)).toBeInTheDocument()
  })
})

describe('the metal in focus', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts on gold, switches to silver, and remembers the choice', () => {
    const { result, rerender } = renderHook(() => useBullionMetal(['GOLD', 'SILVER']))
    expect(result.current[0]).toBe('GOLD')
    act(() => {
      result.current[1]('SILVER')
    })
    rerender()
    expect(result.current[0]).toBe('SILVER')
    expect(renderHook(() => useBullionMetal(['GOLD', 'SILVER'])).result.current[0]).toBe('SILVER')
  })

  it('falls back to the first metal on offer', () => {
    localStorage.setItem('tradedisha.bullionChart', JSON.stringify('COPPER'))
    expect(renderHook(() => useBullionMetal(['SILVER'])).result.current[0]).toBe('SILVER')
  })

  it('offers each metal as a pressed-or-not button', () => {
    const pick = vi.fn()
    render(<MetalSwitch names={['GOLD', 'SILVER']} metal="GOLD" onSelect={pick} />)
    expect(screen.getByRole('button', { name: 'GOLD' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'SILVER' }))
    expect(pick).toHaveBeenCalledWith('SILVER')
  })
})

describe('BullionCards paper trades by hand', () => {
  it('buys or sells each metal future from its card', () => {
    const onTrade = vi.fn()
    render(<BullionCards bullion={bullion} onTrade={onTrade} />)
    fireEvent.click(screen.getByRole('button', { name: 'Buy', description: /GOLD/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Sell', description: /SILVER/ }))
    expect(onTrade.mock.calls).toEqual([
      [{ index: 'GOLD', direction: 'BUY_FUT', strike: null }],
      [{ index: 'SILVER', direction: 'SELL_FUT', strike: null }],
    ])
  })

  it('has no trade buttons without a handler', () => {
    show()
    expect(screen.queryByRole('button', { name: 'Buy' })).not.toBeInTheDocument()
  })
})
