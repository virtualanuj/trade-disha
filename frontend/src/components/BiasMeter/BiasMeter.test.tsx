import { render, screen } from '@testing-library/react'

import type { BiasOut } from '../../api/types'
import { labelColour } from '../../lib/format'
import { BiasMeter } from './BiasMeter'

const bias: BiasOut = {
  index: 'NIFTY',
  minute_ts: 1_700_000_000_000,
  bias: 0.62,
  label: 'Bullish',
  strength: 62,
  is_expiry_day: false,
  group_scores: { trend: 1, oi: 0.2, premium: 0.5 },
  group_weights: { trend: 0.4, oi: 0.35, premium: 0.25 },
  indicators: [],
}

describe('BiasMeter', () => {
  it('shows strength, label and a meter value', () => {
    render(<BiasMeter bias={bias} />)
    expect(screen.getByTestId('bias-meter')).toHaveTextContent('62 Bullish')
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '62')
  })
  it('renders a waiting state without bias', () => {
    render(<BiasMeter bias={undefined} />)
    expect(screen.getByTestId('bias-meter')).toHaveTextContent('waiting for first minute')
  })
  it('maps labels to colours', () => {
    expect(labelColour('Bullish')).toBe('text-bull')
    expect(labelColour('Bearish')).toBe('text-bear')
    expect(labelColour(undefined)).toBe('text-neutral')
  })
})
