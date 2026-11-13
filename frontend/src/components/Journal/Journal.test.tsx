import { fireEvent, render, screen } from '@testing-library/react'

import type { JournalOut, PaperTradeOut } from '../../api/types'
import { trade } from '../OpenTrades/fixtures'
import { Journal } from './Journal'

const closed: PaperTradeOut = {
  ...trade,
  id: 't2',
  status: 'closed',
  exit_price: 131,
  exit_ts: trade.entry_ts + 12 * 60_000,
  exit_reason: 'TARGET',
  exit_fill_quality: 'live',
  gross: 1950,
  net: 1890,
  ltp: null,
  live_gross: null,
  live_net: null,
}
const stale: PaperTradeOut = {
  ...closed,
  id: 't3',
  exit_price: 96,
  exit_reason: 'SQUARE_OFF',
  exit_fill_quality: 'stale',
  exit_price_age_ms: 300_000,
  gross: -325,
  net: -385,
}
const journal: JournalOut = {
  open_trades: 1,
  stats: [
    {
      scope: 'overall',
      trades: 2,
      hits: 1,
      hit_rate: 0.5,
      avg_win: 1890,
      avg_loss: -385,
      net_total: 1505,
      gross_total: 1625,
      avg_duration_s: 720,
      by_reason: { TARGET: 1, SQUARE_OFF: 1 },
      non_live_fills: 1,
    },
  ],
}

describe('Journal', () => {
  it('shows summary figures and badges exits not made on a live price', async () => {
    const load = vi.fn().mockResolvedValue({ trades: [trade, closed, stale], journal })
    render(<Journal indices={['NIFTY', 'BANKNIFTY']} revision={0} load={load} />)

    const card = await screen.findByTestId('stats-overall')
    expect(card).toHaveTextContent('+₹1,505')
    expect(card).toHaveTextContent('50%')
    expect(card).toHaveTextContent('1 of 2 net-positive')
    expect(card).toHaveTextContent('−₹385')
    expect(card).toHaveTextContent('1 exit not on a live price')
    expect(screen.getByTestId('journal')).toHaveTextContent('1 trade is still open')

    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent('open')
    expect(rows[1]).toHaveTextContent('Target')
    expect(rows[1]).toHaveTextContent('+₹1,890')
    expect(rows[2]).toHaveTextContent('stale price 5m old')
  })

  it('filters by exit reason locally and by index on the server', async () => {
    const load = vi.fn().mockResolvedValue({ trades: [closed, stale], journal })
    render(<Journal indices={['NIFTY']} revision={0} load={load} />)
    await screen.findByTestId('stats-overall')

    fireEvent.change(screen.getByLabelText('Exit'), { target: { value: 'SQUARE_OFF' } })
    expect(screen.getAllByRole('row').slice(1)).toHaveLength(1)
    expect(load).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Index'), { target: { value: 'NIFTY' } })
    await screen.findByTestId('stats-overall')
    expect(load).toHaveBeenLastCalledWith(
      { index: 'NIFTY', from: '', to: '' },
      expect.any(AbortSignal),
    )
  })
})
