import { render, screen } from '@testing-library/react'

import type { FlowOut } from '../../api/types'
import { FlowLine } from './FlowLine'

const flow: FlowOut = {
  index: 'NIFTY',
  ts: 1_700_000_000_000,
  score: 0.31,
  fut_book: 0.42,
  fut_trades: null,
  options: -0.1,
  live: false,
}

describe('FlowLine', () => {
  it('shows the score and its parts, and that it is not used yet while in shadow', () => {
    render(<FlowLine flow={flow} />)

    const line = screen.getByTestId('flow-line')
    expect(line).toHaveTextContent('Order flow +0.31')
    expect(line).toHaveTextContent('futures book +0.42')
    expect(line).toHaveTextContent('futures trades —')
    expect(line).toHaveTextContent('options -0.10')
    expect(line).toHaveTextContent('recorded only, not used for signals yet')
    expect(screen.getByText('+0.31')).toHaveClass('text-bull')
  })

  it('drops the note once the trigger is the live rule', () => {
    render(<FlowLine flow={{ ...flow, live: true, score: -0.4 }} />)

    expect(screen.getByTestId('flow-line')).not.toHaveTextContent('not used')
    expect(screen.getByText('-0.40')).toHaveClass('text-bear')
  })

  it('says so when there is no order-flow data', () => {
    render(<FlowLine flow={undefined} />)

    expect(screen.getByTestId('flow-line')).toHaveTextContent('Order flow: no data yet')
  })
})
