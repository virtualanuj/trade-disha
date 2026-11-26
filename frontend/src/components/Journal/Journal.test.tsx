import { fireEvent, render, screen } from '@testing-library/react'

import type { JournalOut } from '../../api/types'
import { Journal } from './Journal'

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
  it('shows summary figures and counts exits not made on a live price', async () => {
    const load = vi.fn().mockResolvedValue(journal)
    render(<Journal indices={['NIFTY', 'BANKNIFTY']} revision={0} load={load} />)

    const card = await screen.findByTestId('stats-overall')
    expect(card).toHaveTextContent('Index options')
    expect(card).toHaveTextContent('+₹1,505')
    expect(card).toHaveTextContent('50%')
    expect(card).toHaveTextContent('1 of 2 net-positive')
    expect(card).toHaveTextContent('−₹385')
    expect(card).toHaveTextContent('Target 1 · Square-off 1')
    expect(card).toHaveTextContent('1 exit not on a live price')
    expect(screen.getByTestId('journal')).toHaveTextContent('1 trade is still open')
  })

  it('lists no trades itself and points to the Trades page', async () => {
    render(<Journal indices={['NIFTY']} revision={0} load={vi.fn().mockResolvedValue(journal)} />)
    await screen.findByTestId('stats-overall')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Exit')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Trades page' })).toHaveAttribute('href', '#trades')
  })

  it('asks the server again for another index or date range', async () => {
    const load = vi.fn().mockResolvedValue(journal)
    render(<Journal indices={['NIFTY']} revision={0} load={load} />)
    await screen.findByTestId('stats-overall')

    fireEvent.change(screen.getByLabelText('Index'), { target: { value: 'NIFTY' } })
    await screen.findByTestId('stats-overall')
    expect(load).toHaveBeenLastCalledWith(
      { index: 'NIFTY', from: '', to: '' },
      expect.any(AbortSignal),
    )
  })
})

describe('Journal trades opened by hand', () => {
  it('shows them in their own card', async () => {
    const overall = journal.stats[0]
    if (!overall) throw new Error('fixture')
    const load = vi.fn().mockResolvedValue({
      ...journal,
      stats: [overall, { ...overall, scope: 'manual', trades: 3 }],
    })
    render(<Journal indices={['NIFTY']} revision={0} load={load} />)
    const card = await screen.findByTestId('stats-manual')
    expect(card).toHaveTextContent('Opened by hand')
    expect(card).toHaveTextContent('3 closed trades')
  })
})
