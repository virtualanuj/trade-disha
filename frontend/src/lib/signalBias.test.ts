import type { IndicatorOut, SignalOut } from '../api/types'
import { biasFromSignal } from './signalBias'

const ind: IndicatorOut = {
  name: 'ema_cross',
  group: 'trend',
  score: 0.8,
  note: 'EMA9 above EMA21',
  quality: 'ok',
  value: {},
  weight: 0.4,
  contribution: 0.32,
  enabled: true,
}

const base = {
  index: 'NIFTY',
  minute_ts: 1_700_000_000_000,
  direction: 'BUY_CE',
  bias: 0.62,
  strength: 62,
  breakdown: {
    indicators: [ind],
    group_scores: { trend: 0.8 },
    group_weights: { trend: 0.4 },
    is_expiry_day: true,
  },
} satisfies Pick<SignalOut, 'index' | 'minute_ts' | 'direction' | 'bias' | 'strength' | 'breakdown'>

describe('biasFromSignal', () => {
  it('rebuilds the market view a signal fired on from its stored breakdown', () => {
    expect(biasFromSignal(base)).toEqual({
      index: 'NIFTY',
      minute_ts: 1_700_000_000_000,
      bias: 0.62,
      label: 'Bullish',
      strength: 62,
      is_expiry_day: true,
      group_scores: { trend: 0.8 },
      group_weights: { trend: 0.4 },
      indicators: [ind],
    })
  })

  it('labels a put or a short future bearish', () => {
    expect(biasFromSignal({ ...base, direction: 'BUY_PE', bias: -0.6 }).label).toBe('Bearish')
    expect(biasFromSignal({ ...base, direction: 'SELL_FUT', bias: -0.6 }).label).toBe('Bearish')
  })

  it('treats missing breakdown fields as empty', () => {
    const b = biasFromSignal({ ...base, breakdown: {} })
    expect(b.indicators).toEqual([])
    expect(b.group_scores).toEqual({})
    expect(b.group_weights).toEqual({})
    expect(b.is_expiry_day).toBe(false)
  })
})
