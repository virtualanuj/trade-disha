import { render, screen } from '@testing-library/react'

import type { JournalOut } from '../../api/types'
import { JournalStats } from './JournalStats'

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

describe('JournalStats', () => {
  it('shows summary figures and counts exits not made on a live price', async () => {
    const load = vi.fn().mockResolvedValue(journal)
    render(<JournalStats query={{}} revision={0} load={load} />)

    const card = await screen.findByTestId('stats-overall')
    expect(card).toHaveTextContent('Index options')
    expect(card).toHaveTextContent('+₹1,505')
    expect(card).toHaveTextContent('50%')
    expect(card).toHaveTextContent('1 of 2 net-positive')
    expect(card).toHaveTextContent('−₹385')
    expect(card).toHaveTextContent('Target 1 · Square-off 1')
    expect(card).toHaveTextContent('1 exit not on a live price')
    expect(screen.getByTestId('journal-stats')).toHaveTextContent('1 trade is still open')
  })

  it('asks the server for the market and dates it is given, and again on a revision', async () => {
    const load = vi.fn().mockResolvedValue(journal)
    const { rerender } = render(
      <JournalStats query={{ index: 'GOLD', from: '2026-11-01' }} revision={0} load={load} />,
    )
    await screen.findByTestId('stats-overall')
    expect(load).toHaveBeenLastCalledWith(
      { index: 'GOLD', from: '2026-11-01', to: '' },
      expect.any(AbortSignal),
    )
    rerender(
      <JournalStats query={{ index: 'GOLD', from: '2026-11-01' }} revision={1} load={load} />,
    )
    await screen.findByTestId('stats-overall')
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('shows trades opened by hand in their own card', async () => {
    const overall = journal.stats[0]
    if (!overall) throw new Error('fixture')
    const load = vi.fn().mockResolvedValue({
      ...journal,
      stats: [overall, { ...overall, scope: 'manual', trades: 3 }],
    })
    render(<JournalStats query={{}} revision={0} load={load} />)
    const card = await screen.findByTestId('stats-manual')
    expect(card).toHaveTextContent('Opened by hand')
    expect(card).toHaveTextContent('3 closed trades')
  })

  it('says when the summary cannot be loaded', async () => {
    const load = vi.fn().mockRejectedValue(new Error('boom'))
    render(<JournalStats query={{}} revision={0} load={load} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the summary: boom')
  })
})
