import { fireEvent, render, screen } from '@testing-library/react'

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
})
