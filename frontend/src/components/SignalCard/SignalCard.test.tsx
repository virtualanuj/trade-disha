import { fireEvent, render, screen } from '@testing-library/react'

import type { SignalOut } from '../../api/types'
import { countdown } from '../../lib/format'
import { trade } from '../OpenTrades/fixtures'
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
  entry_ask: null,
  spread_pct: null,
  entry_mode: 'minute_close',
  shadow: false,
  flow_score: null,
  config_version: null,
  outcome: null,
}

describe('SignalCard', () => {
  it('shows a short bullion future with its point value and gate text', () => {
    const short: SignalOut = {
      ...signal,
      index: 'SILVER',
      direction: 'SELL_FUT',
      strike: 0,
      trading_symbol: 'SILVER FUT 04 DEC 26',
      lot_size: 30,
      entry_price: 170000,
      target_price: 169320,
      stop_price: 170340,
      target_basis: 'pct',
      target_points: null,
      stop_points: null,
      delta_used: null,
    }
    render(<SignalCard signal={short} gate={undefined} now={short.ts_fired} />)
    const card = screen.getByTestId('signal-card')
    expect(card).toHaveTextContent('SELL SILVER FUT')
    expect(card).toHaveTextContent('₹30 per point per lot')
    expect(screen.getByText('SELL SILVER FUT')).toHaveClass('text-bear')
  })

  it('says when bullion signals are switched off', () => {
    render(
      <SignalCard
        signal={undefined}
        gate={{ index: 'GOLD', minute_ts: 0, fired: false, reason: 'disabled' }}
        now={0}
      />,
    )
    expect(screen.getByTestId('signal-card')).toHaveTextContent('switched off')
  })

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

  it('opens a paper trade on click and shows the server reason when refused', async () => {
    const onPaperTrade = vi.fn().mockRejectedValue(new Error('market is not open'))
    render(
      <SignalCard
        signal={signal}
        gate={undefined}
        now={1_700_000_100_000}
        onPaperTrade={onPaperTrade}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Paper trade' }))
    expect(onPaperTrade).toHaveBeenCalledWith(signal)
    expect(await screen.findByRole('alert')).toHaveTextContent('Not opened: market is not open')
  })

  it('disables the action with the reason while the feed is down', () => {
    render(
      <SignalCard
        signal={signal}
        gate={undefined}
        now={1_700_000_100_000}
        blocked="Feed not live: no price to trade at"
        onPaperTrade={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Paper trade' })).toBeDisabled()
    expect(screen.getByTestId('signal-card')).toHaveTextContent('Feed not live')
  })

  it('highlights trades already open on the index, whichever side they are on', () => {
    render(
      <SignalCard
        signal={signal}
        gate={undefined}
        now={trade.entry_ts + 18 * 60_000}
        openTrades={[{ ...trade, direction: 'BUY_PE', live_net: -812 }]}
        onPaperTrade={vi.fn()}
      />,
    )
    const block = screen.getByTestId('signal-open-trades')
    expect(block).toHaveTextContent('1 paper trade already open on NIFTY')
    expect(block).toHaveTextContent('25000 PE @ 101.00')
    expect(block).toHaveTextContent('−₹812')
    expect(block).toHaveTextContent('18m')
    expect(block).toHaveTextContent('opposite side')
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

describe('SignalCard with the order-flow trigger', () => {
  it('explains a setup that is waiting for order flow, or held back by the quote', () => {
    const gate = { index: 'NIFTY', minute_ts: 1_700_000_000_000, fired: false }
    const { rerender } = render(
      <SignalCard signal={undefined} gate={{ ...gate, reason: 'flow_not_confirmed' }} now={0} />,
    )
    expect(screen.getByTestId('signal-card')).toHaveTextContent(
      'setup in place, waiting for order flow to agree',
    )
    rerender(<SignalCard signal={undefined} gate={{ ...gate, reason: 'spread_wide' }} now={0} />)
    expect(screen.getByTestId('signal-card')).toHaveTextContent('bid-ask spread too wide')
    rerender(<SignalCard signal={undefined} gate={{ ...gate, reason: 'no_setup' }} now={0} />)
    expect(screen.getByTestId('signal-card')).toHaveTextContent('bias too weak for a setup')
  })

  it('says a trigger signal is priced at the ask, with the spread', () => {
    render(
      <SignalCard
        signal={{
          ...signal,
          entry_mode: 'trigger',
          entry_price: 150.1,
          entry_ask: 150.1,
          spread_pct: 0.133,
        }}
        gate={undefined}
        now={signal.ts_fired}
      />,
    )
    expect(screen.getByTestId('signal-card')).toHaveTextContent('at the ask · spread 0.13%')
  })
})
