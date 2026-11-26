import { fireEvent, render, screen, within } from '@testing-library/react'

import type { BullionEtfOut, BullionMetalOut, BullionOut } from '../../api/types'
import { BullionCards, EtfCards } from './BullionView'

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
  point_value: 100,
  mini: null,
}
const silver: BullionMetalOut = { ...gold, metal: 'SILVER', trading_symbol: 'SILVER FUT 04 DEC 26' }
const bullion: BullionOut = { metals: [gold, silver], ratio: 79.31, etfs: [] }
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

  it('opens and closes only the card clicked, and remembers each (E31)', () => {
    const { unmount } = show()
    const toggle = (card: string) =>
      within(screen.getByTestId(card)).getByRole('button', { name: /Details/ })
    expect(toggle('bullion-GOLD')).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle('bullion-GOLD'))
    expect(screen.getByTestId('bullion-details-GOLD')).toHaveTextContent('ATP (VWAP)')
    expect(screen.queryByTestId('bullion-details-SILVER')).not.toBeInTheDocument()
    expect(toggle('bullion-SILVER')).toHaveAttribute('aria-expanded', 'false')
    expect(localStorage.getItem('tradedisha.bullionDetailsOpen.GOLD')).toBe('true')
    expect(localStorage.getItem('tradedisha.bullionDetailsOpen.SILVER')).toBeNull()
    expect(localStorage.getItem('tradedisha.detailsOpen')).toBeNull() // the index one is apart

    fireEvent.click(toggle('bullion-SILVER'))
    fireEvent.click(toggle('bullion-GOLD')) // closing gold leaves silver open
    expect(screen.queryByTestId('bullion-details-GOLD')).not.toBeInTheDocument()
    expect(screen.getByTestId('bullion-details-SILVER')).toBeInTheDocument()
    unmount()
    show() // remembered
    expect(screen.queryByTestId('bullion-details-GOLD')).not.toBeInTheDocument()
    expect(screen.getByTestId('bullion-details-SILVER')).toBeInTheDocument()
  })

  it('shows each metal with its day, liquidity, contract and next-month figures', () => {
    localStorage.setItem('tradedisha.bullionDetailsOpen.GOLD', 'true')
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
    localStorage.setItem('tradedisha.bullionDetailsOpen.GOLD', 'true')
    show({ metals: [empty], ratio: null, etfs: [] })
    expect(screen.getByTestId('bullion-ratio')).toHaveTextContent('—')
    expect(screen.getByTestId('bullion-GOLD')).toHaveTextContent('Spread over near—')
  })

  it('explains that bullion needs the live feed', () => {
    show({ metals: [], ratio: null, etfs: [] })
    expect(screen.getByText(/Live feed only/)).toBeInTheDocument()
  })
})

describe('BullionCards paper trades by hand', () => {
  it('buys or sells each metal future from its card', () => {
    const onTrade = vi.fn()
    render(<BullionCards bullion={bullion} onTrade={onTrade} />)
    fireEvent.click(screen.getByRole('button', { name: 'Buy', description: /GOLD/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Sell', description: /SILVER/ }))
    expect(onTrade.mock.calls).toEqual([
      [{ index: 'GOLD', direction: 'BUY_FUT', strike: null, contract: 'GOLD' }],
      [{ index: 'SILVER', direction: 'SELL_FUT', strike: null, contract: 'SILVER' }],
    ])
  })

  it('has no trade buttons without a handler', () => {
    show()
    expect(screen.queryByRole('button', { name: 'Buy' })).not.toBeInTheDocument()
  })
})

const goldbees: BullionEtfOut = {
  metal: 'GOLD',
  symbol: 'GOLDBEES',
  ltp: 108.42,
  prev_close: 107.81,
  change: 0.61,
  change_pct: 0.57,
  day_open: 107.9,
  day_high: 108.6,
  day_low: 107.5,
  range_pos: 0.84,
  atp: 108.1,
  volume: 1_234_567,
  bid: 108.41,
  ask: 108.43,
  bid_qty: 900,
  ask_qty: 1200,
  spread: 0.02,
  range_high: 110,
  range_low: 70,
  updated_ts: 1_794_820_957_000,
}
const silverbees: BullionEtfOut = { ...goldbees, metal: 'SILVER', symbol: 'SILVERBEES' }
describe('EtfCards: NSE BULLION (E25, E32)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows both ETFs, with their price and change', () => {
    render(<EtfCards etfs={[goldbees, silverbees]} nseStatus="live" />)
    const cards = screen.getAllByTestId(/^(bullion|etf)-[A-Z]+$/).map((el) => el.dataset.testid)
    expect(cards).toEqual(['etf-GOLDBEES', 'etf-SILVERBEES'])
    const g = screen.getByTestId('etf-GOLDBEES')
    expect(g).toHaveTextContent('LTP ₹ / unit')
    expect(g).toHaveTextContent('108.42')
    expect(g).toHaveTextContent('+0.61 (+0.57%)')
    expect(g).not.toHaveTextContent('NSE closed')
  })

  it('opens its own details only, and has no trade buttons', () => {
    render(<EtfCards etfs={[goldbees, silverbees]} nseStatus="live" />)
    expect(screen.queryByRole('button', { name: 'Buy' })).not.toBeInTheDocument()
    fireEvent.click(
      within(screen.getByTestId('etf-GOLDBEES')).getByRole('button', { name: /Details/ }),
    )
    const d = screen.getByTestId('etf-details-GOLDBEES')
    expect(d).toHaveTextContent('Prev close107.81')
    expect(d).toHaveTextContent('Bid108.41 × 900')
    expect(d).toHaveTextContent('Spread0.02')
    expect(d).toHaveTextContent('52 weeks')
    expect(d).toHaveTextContent('High110.00')
    expect(d).not.toHaveTextContent('Open interest')
    expect(screen.queryByTestId('etf-details-SILVERBEES')).not.toBeInTheDocument()
  })

  it('says when NSE is not trading', () => {
    render(<EtfCards etfs={[goldbees, silverbees]} nseStatus="closed" />)
    expect(screen.getByTestId('etf-GOLDBEES')).toHaveTextContent('NSE closed')
    expect(screen.getByTestId('etf-SILVERBEES')).toHaveTextContent('NSE closed')
  })

  it('explains that the ETFs need the live feed', () => {
    render(<EtfCards etfs={[]} />)
    expect(screen.getByText(/GOLDBEES and SILVERBEES come from NSE/)).toBeInTheDocument()
  })
})

describe('BullionCards minis (E28)', () => {
  const goldm: BullionMetalOut = {
    ...gold,
    metal: 'GOLDM',
    trading_symbol: 'GOLDM FUT 04 DEC 26',
    lot_size: 100,
    point_value: 10,
    ltp: 134_950,
    change: -1750,
    change_pct: -1.28,
    next_symbol: 'GOLDM FUT 05 JAN 27',
  }
  const withMini: BullionOut = { ...bullion, metals: [{ ...gold, mini: goldm }, silver] }

  it('shows the mini under its metal, with its price and point value', () => {
    render(<BullionCards bullion={withMini} />)
    const cards = screen.getAllByTestId(/^(bullion|mini)-[A-Z]+$/).map((el) => el.dataset.testid)
    expect(cards).toEqual(['bullion-GOLD', 'mini-GOLDM', 'bullion-SILVER'])
    const m = screen.getByTestId('mini-GOLDM')
    expect(m).toHaveTextContent('GOLDM FUT 04 DEC 26 · exp 04/12/2026 · lot 100 · ₹10 / point')
    expect(m).toHaveTextContent('LTP ₹ / 10 g')
    expect(m).toHaveTextContent('1,34,950.00')
    expect(m).toHaveTextContent('-1750.00 (-1.28%)')
    expect(m).not.toHaveTextContent('Spread') // the figures are behind Details, as for gold
  })

  it('opens the same details as its metal, on its own toggle', () => {
    render(<BullionCards bullion={withMini} />)
    fireEvent.click(
      within(screen.getByTestId('mini-GOLDM')).getByRole('button', { name: /Details/ }),
    )
    const d = screen.getByTestId('bullion-details-GOLDM')
    expect(d).toHaveTextContent('ATP (VWAP)')
    expect(d).toHaveTextContent('Open interest')
    expect(d).toHaveTextContent('Contract, 1 year')
    expect(d).toHaveTextContent('Upper circuit')
    expect(d).toHaveTextContent('Spread20.00')
    expect(d).toHaveTextContent('Next month')
    expect(screen.queryByTestId('bullion-details-GOLD')).not.toBeInTheDocument()
  })

  it('buys or sells the mini from its own card', () => {
    const onTrade = vi.fn()
    render(<BullionCards bullion={withMini} onTrade={onTrade} />)
    fireEvent.click(screen.getByRole('button', { name: 'Sell', description: /GOLDM/ }))
    expect(onTrade).toHaveBeenCalledWith({
      index: 'GOLD',
      direction: 'SELL_FUT',
      strike: null,
      contract: 'GOLDM',
    })
  })
})

describe('BullionCards on an MCX tab (E29, E32)', () => {
  const both: BullionOut = {
    ...bullion,
    metals: [
      {
        ...gold,
        mini: { ...gold, metal: 'GOLDM', trading_symbol: 'GOLDM FUT 04 DEC 26', mini: null },
      },
      silver,
    ],
    etfs: [{ ...goldbees }, { ...silverbees }],
  }
  const shown = () =>
    screen.getAllByTestId(/^(bullion|mini|etf)-[A-Z]+$/).map((el) => el.dataset.testid)

  it('shows only gold and its mini on GOLD; the ETFs are on NSE', () => {
    render(<BullionCards bullion={both} metal="GOLD" />)
    expect(shown()).toEqual(['bullion-GOLD', 'mini-GOLDM'])
    expect(screen.getByTestId('bullion-ratio')).toHaveTextContent('79.31') // still both metals'
  })

  it('shows only silver on SILVER', () => {
    render(<BullionCards bullion={both} metal="SILVER" />)
    expect(shown()).toEqual(['bullion-SILVER'])
  })

  it('shows every metal with no focus, or one it does not have', () => {
    const { unmount } = render(<BullionCards bullion={both} />)
    expect(shown()).toEqual(['bullion-GOLD', 'mini-GOLDM', 'bullion-SILVER'])
    unmount()
    render(<BullionCards bullion={both} metal="COPPER" />)
    expect(shown()).toHaveLength(3)
  })
})
