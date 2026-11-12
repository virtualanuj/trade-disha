import { render, screen } from '@testing-library/react'

import type { ResolvedIndexOut } from '../../api/types'
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
    expect(screen.getByText(/exp 2026-11-17/)).toBeInTheDocument()
  })
})
