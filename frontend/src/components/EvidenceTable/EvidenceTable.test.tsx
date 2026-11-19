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
          name: 'gift_nifty',
          group: 'macro',
          score: 0.4,
          note: 'GIFT Nifty +0.30% overnight, follow, 67% weight left',
          quality: 'ok',
          value: { move_pct: 0.3, fade: 0.67 },
          weight: 0.05,
          contribution: 0.02,
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
    expect(screen.getByText('Macro: dollar, crude, metals')).toBeInTheDocument()
    expect(screen.getByText('Crude oil')).toBeInTheDocument()
    expect(screen.getByText('Crude +0.40% in 30 min')).toBeInTheDocument()
    expect(screen.getByText('GIFT Nifty gap')).toBeInTheDocument()
    const silver = screen.getByText('Silver').closest('tr')
    expect(silver).toHaveClass('text-fg-muted/70')
    expect(silver).not.toHaveTextContent('(info)') // its note already says it is not scored
  })

  it('shows bullion positioning, order flow and the other metal', () => {
    const row = (
      name: string,
      group: 'oi' | 'flow' | 'macro',
      note: string,
    ): BiasOut['indicators'][number] => ({
      name,
      group,
      score: 0.5,
      note,
      quality: 'ok',
      value: {},
      weight: 0.075,
      contribution: 0.0375,
    })
    const gold: BiasOut = {
      ...bias,
      index: 'GOLD',
      group_scores: { trend: 0.75, oi: 0.5, premium: 0, flow: 0.5, macro: 0.5 },
      group_weights: { trend: 0.6, oi: 0.15, premium: 0, flow: 0.15, macro: 0.1 },
      indicators: [
        ...bias.indicators.slice(0, 1),
        row('futures_oi', 'oi', 'long build-up: price +0.20%, OI +0.40% in 15 min'),
        row('net_volume', 'flow', 'net buying 25% of 1,200 traded in 15 min'),
        row('book_imbalance', 'flow', 'book lean +0.05 against -0.15 over 30 min'),
        row('peer_metal', 'macro', 'SILVER trend +0.50'),
      ],
    }
    render(<EvidenceTable bias={gold} />)
    const t = screen.getByTestId('evidence')
    for (const text of [
      'Open interest',
      'Futures OI build-up',
      'Order flow',
      'Net traded volume',
      'Order-book lean',
      'Other metal’s trend',
      'SILVER trend +0.50',
    ]) {
      expect(t).toHaveTextContent(text)
    }
    expect(t).not.toHaveTextContent('Premium behaviour')
  })

  it('leaves the index without an order-flow group', () => {
    render(<EvidenceTable bias={bias} />)
    expect(screen.queryByText('Order flow')).not.toBeInTheDocument()
  })

  it('leaves the macro group out when it has no weight and no readings', () => {
    render(<EvidenceTable bias={bias} />)
    expect(screen.queryByText(/Macro/)).not.toBeInTheDocument()
  })
})
