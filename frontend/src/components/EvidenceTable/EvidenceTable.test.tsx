import { render, screen } from '@testing-library/react'

import type { BiasOut } from '../../api/types'
import { EvidenceTable } from './EvidenceTable'

const bias: BiasOut = {
  index: 'NIFTY',
  minute_ts: 0,
  bias: 0.3,
  label: 'Bullish',
  strength: 30,
  is_expiry_day: false,
  group_scores: { trend: 0.75, oi: 0, premium: 0 },
  group_weights: { trend: 0.4, oi: 0.35, premium: 0.25 },
  indicators: [
    {
      name: 'ema_cross',
      group: 'trend',
      score: 0.75,
      note: 'EMA9 above EMA21 by 0.12%',
      quality: 'ok',
      value: { sep_pct: 0.12 },
      weight: 0.4,
      contribution: 0.3,
    },
    {
      name: 'pcr',
      group: 'oi',
      score: 0,
      note: 'warming up (0/1 bars)',
      quality: 'warming',
      value: {},
      weight: 0,
      contribution: 0,
    },
  ],
}

describe('EvidenceTable', () => {
  it('lists indicators under their groups with notes and contributions', () => {
    render(<EvidenceTable bias={bias} />)
    const t = screen.getByTestId('evidence')
    expect(t).toHaveTextContent('Price trend')
    expect(t).toHaveTextContent('EMA crossover')
    expect(t).toHaveTextContent('EMA9 above EMA21 by 0.12%')
    expect(t).toHaveTextContent('+0.300')
    expect(t).toHaveTextContent('(warming)')
  })
  it('shows a placeholder before the first bias', () => {
    render(<EvidenceTable bias={undefined} />)
    expect(screen.getByText(/after the first minute/)).toBeInTheDocument()
  })
})
