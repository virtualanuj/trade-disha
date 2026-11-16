import { fireEvent, render, screen } from '@testing-library/react'

import type { BullionMetalOut, BullionOut, CandleOut } from '../../api/types'
import { BullionView } from './BullionView'

vi.mock('../PriceChart/PriceChart', () => ({
  PriceChart: ({ dataKey, candles }: { dataKey: string; candles: CandleOut[] }) => (
    <div data-testid="chart">
      {dataKey}:{candles.length}
    </div>
  ),
}))

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
const candle = (t: number): CandleOut => ({ t, o: 1, h: 1, l: 1, c: 1, v: 1, synthetic: false })

function show(b: BullionOut | null = bullion) {
  return render(
    <BullionView
      bullion={b}
      candles={{ GOLD: [candle(1), candle(2)], SILVER: [candle(1)] }}
      overlays={{}}
      theme="dark"
      chartHeight={300}
    />,
  )
}

describe('BullionView', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows each metal with its day, liquidity, contract and next-month figures', () => {
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

  it('charts gold first, switches to silver, and remembers the choice', () => {
    show()
    expect(screen.getByTestId('chart')).toHaveTextContent('bullion-GOLD:2')
    fireEvent.click(screen.getByRole('button', { name: 'SILVER' }))
    expect(screen.getByTestId('chart')).toHaveTextContent('bullion-SILVER:1')
    expect(screen.getByRole('button', { name: 'SILVER' })).toHaveAttribute('aria-pressed', 'true')
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
    show({ metals: [empty], ratio: null })
    expect(screen.getByTestId('bullion-ratio')).toHaveTextContent('—')
    expect(screen.getByTestId('bullion-GOLD')).toHaveTextContent('Spread over near—')
  })

  it('explains that bullion needs the live feed', () => {
    show({ metals: [], ratio: null })
    expect(screen.getByText(/Live feed only/)).toBeInTheDocument()
    expect(screen.queryByTestId('chart')).toBeNull()
  })
})
