import { render, screen } from '@testing-library/react'

import type { SignalOut } from '../../api/types'
import { countdown } from '../../lib/format'
import { SignalCard } from './SignalCard'

const signal: SignalOut = {
  id: 'abc',
  index: 'NIFTY',
  minute_ts: 1_700_000_000_000,
  ts_fired: 1_700_000_060_000,
  direction: 'BUY_CE',
  instrument_key: 'NSE_FO|X',
  trading_symbol: 'NIFTY17NOV2625000CE',
  strike: 25000,
  expiry: '2026-11-17',
  lot_size: 75,
  entry_price: 150,
  target_price: 195,
  stop_price: 127.5,
  target_basis: 'pct',
  target_points: null,
  stop_points: null,
  delta_used: null,
  bias: 0.62,
  strength: 62,
  breakdown: {
    indicators: [
      {
        name: 'ema_cross',
        group: 'trend',
        score: 0.8,
        note: 'EMA9 above EMA21 by 0.10%',
        quality: 'ok',
        value: {},
        weight: 0.4,
        contribution: 0.32,
      },
    ],
  },
  expires_at: 1_700_000_360_000,
  status: 'active',
  status_ts: 1_700_000_060_000,
}

describe('SignalCard', () => {
  it('shows the option, levels, countdown and reasons', () => {
    render(<SignalCard signal={signal} gate={undefined} now={1_700_000_100_000} />)
    const card = screen.getByTestId('signal-card')
    expect(card).toHaveTextContent('BUY NIFTY 25000 CE')
    expect(card).toHaveTextContent('195.00')
    expect(card).toHaveTextContent('127.50')
    expect(card).toHaveTextContent('4:20')
    expect(card).toHaveTextContent('EMA9 above EMA21 by 0.10%')
    expect(screen.getByRole('button', { name: 'Paper trade' })).toBeDisabled()
  })

  it('explains why nothing fired', () => {
    render(
      <SignalCard
        signal={undefined}
        gate={{ index: 'NIFTY', minute_ts: 0, fired: false, reason: 'below_threshold' }}
        now={0}
      />,
    )
    expect(screen.getByTestId('signal-card')).toHaveTextContent('bias below the entry threshold')
  })

  it('formats the countdown', () => {
    expect(countdown(65_000, 0)).toBe('1:05')
    expect(countdown(0, 5_000)).toBe('0:00')
  })
})
