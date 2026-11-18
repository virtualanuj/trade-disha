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
  it('shows only the trend group for bullion, which has no option chain', () => {
    const gold: BiasOut = {
      ...bias,
      index: 'GOLD',
      group_scores: { trend: 0.75, oi: 0, premium: 0 },
      group_weights: { trend: 1, oi: 0, premium: 0 },
      indicators: [
        {
          name: 'ema_cross',
          group: 'trend',
          score: 0.75,
          note: 'EMA9 above EMA21 by 0.12%',
          quality: 'ok',
          value: {},
          weight: 1,
          contribution: 0.75,
        },
      ],
    }
    render(<EvidenceTable bias={gold} />)
    const t = screen.getByTestId('evidence')
    expect(t).toHaveTextContent('Price trend')
    expect(t).not.toHaveTextContent('Open interest')
    expect(t).not.toHaveTextContent('Premium behaviour')
  })

  it('keeps an index group with weight even before its indicators report', () => {
    render(<EvidenceTable bias={bias} />)
    expect(screen.getByTestId('evidence')).toHaveTextContent('Premium behaviour')
  })

  it('shows a placeholder before the first bias', () => {
    render(<EvidenceTable bias={undefined} />)
    expect(screen.getByText(/after the first minute/)).toBeInTheDocument()
  })

  it('shows the macro group with its readings, silver muted as not scored', () => {
    const withMacro: BiasOut = {
      ...bias,
      group_scores: { ...bias.group_scores, macro: -0.5 },
      group_weights: { trend: 0.36, oi: 0.315, premium: 0.225, macro: 0.1 },
      indicators: [
        ...bias.indicators,
        {
          name: 'crude',
          group: 'macro',
          score: -0.5,
          note: 'Crude +0.40% in 30 min',
          quality: 'ok',
          value: { change_pct: 0.4 },
          weight: 0.05,
          contribution: -0.025,
        },
        {
          name: 'silver',
          group: 'macro',
          score: 0,
          note: 'Silver +1.00% in 30 min (shown, not scored)',
          quality: 'info',
          value: { change_pct: 1 },
          weight: 0,
          contribution: 0,
        },
      ],
    }
    render(<EvidenceTable bias={withMacro} />)
    expect(screen.getByText('Macro: dollar, crude, gold')).toBeInTheDocument()
    expect(screen.getByText('Crude oil')).toBeInTheDocument()
    expect(screen.getByText('Crude +0.40% in 30 min')).toBeInTheDocument()
    const silver = screen.getByText('Silver').closest('tr')
    expect(silver).toHaveClass('text-fg-muted/70')
    expect(silver).not.toHaveTextContent('(info)') // its note already says it is not scored
  })

  it('leaves the macro group out when it has no weight and no readings', () => {
    render(<EvidenceTable bias={bias} />)
    expect(screen.queryByText(/Macro/)).not.toBeInTheDocument()
  })
})
