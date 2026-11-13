import { fireEvent, render, screen } from '@testing-library/react'

import type { IndexPrices, IndexStatsOut, ResolvedIndexOut } from '../../api/types'
import { IndexTiles } from './IndexTiles'

const inst = (key: string, type: ResolvedIndexOut['spot']['instrument_type']) => ({
  instrument_key: key,
  trading_symbol: key,
  instrument_type: type,
  expiry: type === 'INDEX' ? null : '2026-11-24',
  strike: null,
  lot_size: 75,
})

const nifty: ResolvedIndexOut = {
  index: 'NIFTY',
  spot: inst('NSE_INDEX|Nifty 50', 'INDEX'),
  future: inst('NSE_FO|NIFTYFUT', 'FUT'),
  options_expiry: '2026-11-17',
  is_expiry_day: false,
  strike_step: 50,
  atm: 25000,
  lot_size: 75,
  strikes: [],
}

const prices: IndexPrices = {
  index: 'NIFTY',
  spot_ltp: 25060,
  spot_ts: 1_700_000_000_000,
  fut_ltp: 25095.5,
  fut_ts: 1_700_000_000_000,
}

const stats: IndexStatsOut = {
  index: 'NIFTY',
  day_open: 25000,
  day_high: 25100,
  day_low: 24980,
  range_pos: 0.6667,
  prev_close: 24900,
  change: 160,
  change_pct: 0.64,
  high_52w: 26300,
  low_52w: 21700,
  fut_premium: 35.5,
  vix: 13.2,
  vix_change_pct: 10,
  updated_ts: 1_700_000_000_000,
}

describe('IndexTiles', () => {
  it('renders a placeholder before instruments arrive', () => {
    render(<IndexTiles instruments={[]} prices={{}} />)
    expect(screen.getByText(/Waiting for instruments/)).toBeInTheDocument()
  })

  it('renders spot and futures prices in Indian format', () => {
    render(
      <IndexTiles
        instruments={[nifty]}
        prices={{
          NIFTY: {
            index: 'NIFTY',
            spot_ltp: 25012.5,
            spot_ts: 1_700_000_000_000,
            fut_ltp: 25050,
            fut_ts: 1_700_000_000_000,
          },
        }}
      />,
    )
    expect(screen.getByText('25,012.50')).toBeInTheDocument()
    expect(screen.getByText('25,050.00')).toBeInTheDocument()
    expect(screen.getByText(/exp 17\/11\/2026/)).toBeInTheDocument()
    expect(screen.getByText('Fut 24/11/2026')).toBeInTheDocument()
  })

  it('keeps the details closed until asked, then shows every group', () => {
    render(<IndexTiles instruments={[nifty]} prices={{ NIFTY: prices }} stats={{ NIFTY: stats }} />)
    expect(screen.queryByTestId('index-details')).not.toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: /Details/ })
    expect(toggle).toHaveTextContent('+160.00 (+0.64%)') // the day's change shows while closed

    fireEvent.click(toggle)

    const d = screen.getByTestId('index-details')
    expect(d).toHaveTextContent('Open25,000.00')
    expect(d).toHaveTextContent('High25,100.00')
    expect(d).toHaveTextContent('Low24,980.00')
    expect(d).toHaveTextContent('High26,300.00-4.7%')
    expect(d).toHaveTextContent('Low21,700.00+15.5%')
    expect(d).toHaveTextContent('Prev close24,900.00')
    expect(d).toHaveTextContent('Premium over spot+35.50')
    expect(d).toHaveTextContent('VIX13.20+10.00%')
    expect(
      screen.getByRole('img', { name: "Position in the day's range: 67%" }),
    ).toBeInTheDocument()
    expect(localStorage.getItem('tradedisha.detailsOpen')).toBe('true')
  })

  it('shows a dash for what the feed cannot supply', () => {
    localStorage.setItem('tradedisha.detailsOpen', 'true')
    const bare = {
      ...stats,
      prev_close: null,
      change: null,
      change_pct: null,
      high_52w: null,
      low_52w: null,
      vix: null,
      vix_change_pct: null,
    }
    render(<IndexTiles instruments={[nifty]} prices={{ NIFTY: prices }} stats={{ NIFTY: bare }} />)
    const d = screen.getByTestId('index-details')
    expect(d).toHaveTextContent('Prev close—')
    expect(d).toHaveTextContent('VIX—')
    expect(d).toHaveTextContent('High—')
    expect(screen.queryByRole('img', { name: /52-week range/ })).not.toBeInTheDocument()
  })
})
