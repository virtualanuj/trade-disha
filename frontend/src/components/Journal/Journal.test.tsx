import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import type { StatementQuery } from '../../api/client'
import type { BankStatementOut, StatementRowOut } from '../../api/types'
import { Journal } from './Journal'

const T0 = Date.UTC(2026, 10, 20, 4, 0) // 20/11/2026 09:30 IST

const cashMove = {
  trade_id: null,
  index: null,
  direction: null,
  strike: null,
  trading_symbol: null,
} as const

const rows: StatementRowOut[] = [
  {
    ...cashMove,
    ts: T0,
    kind: 'OPEN',
    held: 0,
    cash: 2_500_000,
    balance: 2_500_000,
    blocked: 0,
    available: 2_500_000,
  },
  {
    ts: T0 + 600_000,
    kind: 'BLOCK',
    held: 7_635,
    cash: 0,
    balance: 2_500_000,
    blocked: 7_635,
    available: 2_492_365,
    trade_id: 't1',
    index: 'NIFTY',
    direction: 'BUY_CE',
    strike: 25_000,
    trading_symbol: 'NIFTY 25000 CE',
  },
  {
    ts: T0 + 1_800_000,
    kind: 'SETTLE',
    held: -7_635,
    cash: 1_740,
    balance: 2_501_740,
    blocked: 0,
    available: 2_501_740,
    trade_id: 't1',
    index: 'NIFTY',
    direction: 'BUY_CE',
    strike: 25_000,
    trading_symbol: 'NIFTY 25000 CE',
  },
  {
    ...cashMove,
    ts: T0 + 3_600_000,
    kind: 'WITHDRAW',
    held: 0,
    cash: -2_600_000,
    balance: -98_260,
    blocked: 0,
    available: -98_260,
  },
]

function setup(statement: BankStatementOut = { rows }) {
  const load = vi.fn<(q: StatementQuery, signal: AbortSignal) => Promise<BankStatementOut>>(() =>
    Promise.resolve(statement),
  )
  const page = (revision: number, cashMoves: number) => (
    <Journal
      markets={['NIFTY', 'GOLD']}
      revision={revision}
      cashMoves={cashMoves}
      bank={<div data-testid="bank-strip" />}
      load={load}
    />
  )
  const view = render(page(0, 1))
  return {
    load,
    rerender: (revision: number, cashMoves: number) => {
      view.rerender(page(revision, cashMoves))
    },
  }
}

describe('Journal: the paper bank statement', () => {
  it('lists every cash move with the figures after it, under the bank strip', async () => {
    setup()
    const lines = await screen.findAllByTestId('statement-row')
    expect(screen.getByTestId('bank-strip')).toBeInTheDocument()
    expect(lines).toHaveLength(4)
    const blockRow = lines[1]
    if (!blockRow) throw new Error('rows')

    expect(lines[0]).toHaveTextContent('20/11/2026 09:30')
    expect(lines[0]).toHaveTextContent('Opening deposit')
    expect(lines[0]).toHaveTextContent('₹25,00,000')

    expect(lines[1]).toHaveTextContent('Blocked')
    expect(within(blockRow).getByRole('link', { name: 'NIFTY 25000 CE' })).toHaveAttribute(
      'href',
      '#trades',
    )
    expect(lines[1]).toHaveTextContent('+₹7,635')
    expect(lines[1]).toHaveTextContent('₹24,92,365')

    expect(lines[2]).toHaveTextContent('Settled')
    expect(lines[2]).toHaveTextContent('−₹7,635')
    expect(lines[2]).toHaveTextContent('+₹1,740')
    expect(lines[2]).toHaveTextContent('₹25,01,740')

    expect(lines[3]).toHaveTextContent('Withdrawal')
    expect(lines[3]).toHaveTextContent('−₹26,00,000')
    expect(lines[3]).toHaveTextContent('−₹98,260')
  })

  it('no longer shows the summary cards, and points to the Trades page', async () => {
    setup()
    await screen.findAllByTestId('statement-row')
    expect(screen.queryByTestId('stats-overall')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Trades page' })).toHaveAttribute('href', '#trades')
  })

  it('asks the server for the market, kind and dates chosen', async () => {
    const { load } = setup()
    await screen.findAllByTestId('statement-row')
    expect(load).toHaveBeenLastCalledWith(
      { index: '', kind: '', from: '', to: '' },
      expect.any(AbortSignal),
    )
    fireEvent.change(screen.getByLabelText('Market'), { target: { value: 'GOLD' } })
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'SETTLE' } })
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01' } })
    await waitFor(() => {
      expect(load).toHaveBeenLastCalledWith(
        { index: 'GOLD', kind: 'SETTLE', from: '2026-11-01', to: '' },
        expect.any(AbortSignal),
      )
    })
  })

  it('refetches when a trade changes or cash moves', async () => {
    const { load, rerender } = setup()
    await screen.findAllByTestId('statement-row')
    expect(load).toHaveBeenCalledTimes(1)
    rerender(1, 1)
    await waitFor(() => {
      expect(load).toHaveBeenCalledTimes(2)
    })
    rerender(1, 2)
    await waitFor(() => {
      expect(load).toHaveBeenCalledTimes(3)
    })
  })

  it('says when nothing matches', async () => {
    setup({ rows: [] })
    expect(await screen.findByText('No cash moves match.')).toBeInTheDocument()
  })

  it('shows the error from the server', async () => {
    const load = vi.fn().mockRejectedValue(new Error('boom'))
    render(<Journal markets={[]} revision={0} cashMoves={0} load={load} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the statement: boom')
  })
})
