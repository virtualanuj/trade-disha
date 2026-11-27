import { render, screen } from '@testing-library/react'

import type { PaperTradeOut } from '../../api/types'
import { trade } from '../OpenTrades/fixtures'
import { TradeSummary } from './TradeSummary'

const closed = (id: string, net: number, over: Partial<PaperTradeOut> = {}): PaperTradeOut => ({
  ...trade,
  id,
  status: 'closed',
  entry_price: 100,
  stop_price: 90,
  qty: 10,
  cost: 20,
  gross: net + 20,
  net,
  exit_ts: trade.entry_ts + 10 * 60_000,
  exit_reason: net > 0 ? 'TARGET' : 'STOP',
  exit_fill_quality: 'live',
  live_net: null,
  ...over,
})

describe('TradeSummary', () => {
  it('shows nothing with no trades', () => {
    const { container } = render(<TradeSummary trades={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the headline figures and a row per market', () => {
    const t0 = trade.entry_ts
    render(
      <TradeSummary
        trades={[
          closed('a', 300, { entry_ts: t0 }),
          closed('b', -100, { entry_ts: t0 + 60_000, index: 'BANKNIFTY' }),
          closed('c', -50, { entry_ts: t0 + 120_000, exit_fill_quality: 'stale' }),
          { ...trade, id: 'o', live_net: 590 },
        ]}
      />,
    )
    expect(screen.getByTestId('summary-net')).toHaveTextContent('+₹150')
    expect(screen.getByTestId('summary-net')).toHaveTextContent('cost −₹60')
    expect(screen.getByTestId('summary-hit')).toHaveTextContent('33%')
    expect(screen.getByTestId('summary-hit')).toHaveTextContent('1 won · 2 lost')
    expect(screen.getByTestId('summary-pf')).toHaveTextContent('2.00')
    expect(screen.getByTestId('summary-expectancy')).toHaveTextContent('+₹50')
    expect(screen.getByTestId('summary-expectancy')).toHaveTextContent('avg +0.50R')
    expect(screen.getByTestId('summary-best')).toHaveTextContent('+₹300 / −₹100')
    expect(screen.getByTestId('summary-drawdown')).toHaveTextContent('−₹150')
    expect(screen.getByTestId('summary-drawdown')).toHaveTextContent('worst run 2 losses')
    expect(screen.getByTestId('summary-open')).toHaveTextContent('+₹590')
    expect(screen.getByTestId('summary-footnote')).toHaveTextContent('Target 1 · Stop 2')
    expect(screen.getByTestId('summary-footnote')).toHaveTextContent('1 exit not on a live price')
    expect(screen.getByTestId('summary-row-overall')).toHaveTextContent('1–2')
    expect(screen.getByTestId('summary-row-NIFTY')).toHaveTextContent('+₹250')
    expect(screen.getByTestId('summary-row-BANKNIFTY')).toHaveTextContent('−₹100')
  })
})
