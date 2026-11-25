import { act, fireEvent, render, screen } from '@testing-library/react'

import type { PaperTradeOut } from '../../api/types'
import { trade } from './fixtures'
import { OpenTrades } from './OpenTrades'

describe('OpenTrades', () => {
  it('says so when no trade is open, rather than disappearing', () => {
    render(<OpenTrades trades={[]} now={0} canClose />)
    expect(screen.getByTestId('open-trades')).toHaveTextContent('No open paper trades.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows live net P&L, time open and the bias-reversed flag', () => {
    render(
      <OpenTrades
        trades={[{ ...trade, warning: 'bias_reversed' }]}
        now={trade.entry_ts + 18 * 60_000}
        canClose
      />,
    )
    const panel = screen.getByTestId('open-trades')
    expect(panel).toHaveTextContent('25000 CE')
    expect(panel).toHaveTextContent('+₹590')
    expect(panel).toHaveTextContent('18m')
    expect(panel).toHaveTextContent('bias reversed')
  })

  it('closes on click and reports a refusal', async () => {
    const onClose = vi.fn().mockRejectedValue(new Error('feed is not live'))
    render(<OpenTrades trades={[trade]} now={trade.entry_ts} canClose onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledWith('t1')
    expect(await screen.findByRole('alert')).toHaveTextContent('Not closed: feed is not live')
  })

  it('cannot close while the feed is down', () => {
    render(<OpenTrades trades={[trade]} now={trade.entry_ts} canClose={false} />)
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled()
  })

  it('keeps each row busy until its own request ends, and says which trade was refused', async () => {
    const b: PaperTradeOut = { ...trade, id: 't2', strike: 25100, trading_symbol: 'B' }
    const answers: Record<string, { ok: (v: unknown) => void; no: (e: Error) => void }> = {}
    const onClose = vi.fn(
      (id: string) =>
        new Promise((ok, no) => {
          answers[id] = { ok, no }
        }),
    )
    render(<OpenTrades trades={[trade, b]} now={trade.entry_ts} canClose onClose={onClose} />)
    const [closeA, closeB] = screen.getAllByRole('button', { name: 'Close' })
    if (!closeA || !closeB) throw new Error('two rows expected')
    fireEvent.click(closeA)
    fireEvent.click(closeB)
    expect(closeA).toBeDisabled()
    expect(closeB).toBeDisabled()

    await act(async () => {
      answers.t2?.no(new Error('feed is not live')) // B is refused first
      await Promise.resolve()
    })
    expect(closeA).toBeDisabled() // A is still in flight: no second close can be sent
    expect(closeA).toHaveTextContent('Closing…')
    expect(closeB).toBeEnabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Not closed: feed is not live')
    expect(screen.getByRole('alert')).toHaveTextContent('25100 CE')

    await act(async () => {
      answers.t1?.ok({})
      await Promise.resolve()
    })
    expect(closeA).toBeEnabled()
    expect(screen.getAllByRole('alert')).toHaveLength(1) // A's success does not clear B's refusal
  })
})
