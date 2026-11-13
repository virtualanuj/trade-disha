import type {
  BiasOut,
  CandleOut,
  ChainOut,
  IndexPrices,
  IndexStatsOut,
  PaperTradeOut,
  SignalOut,
} from '../api/types'
import {
  biasSummary,
  chainSummary,
  chartSummary,
  evidenceSummary,
  historySummary,
  signalSummary,
  tilesSummary,
  tradesSummary,
} from './panelSummary'

const signal = (over: Partial<SignalOut> = {}): SignalOut =>
  ({
    id: 's1',
    index: 'NIFTY',
    direction: 'BUY_CE',
    strike: 24800,
    entry_price: 112,
    expires_at: 130_000,
    status: 'active',
    ...over,
  }) as SignalOut

describe('panel summaries', () => {
  it('index: spot and change on the day', () => {
    const prices = { spot_ltp: 24812.4 } as IndexPrices
    const stats = { change_pct: 0.42 } as IndexStatsOut
    expect(tilesSummary(prices, stats)).toBe('24,812.40 · +0.42%')
    expect(tilesSummary(prices, undefined)).toBe('24,812.40')
    expect(tilesSummary(undefined, undefined)).toBe('—')
  })

  it('market view: strength and label', () => {
    expect(biasSummary({ strength: 42, label: 'Bullish' } as BiasOut)).toBe('42 Bullish')
    expect(biasSummary(undefined)).toBe('—')
  })

  it('signal: what to buy, the entry and the time left', () => {
    expect(signalSummary(signal(), 0)).toBe('24800 CE · entry 112.00 · 2:10 left')
    expect(signalSummary(signal({ direction: 'BUY_PE' }), 0)).toContain('24800 PE')
    expect(signalSummary(undefined, 0)).toBe('No signal')
  })

  it('open trades: how many and the live profit or loss', () => {
    const trades = [{ live_net: 1000 }, { live_net: 240.4 }] as PaperTradeOut[]
    expect(tradesSummary(trades)).toBe('2 open · +₹1,240')
    expect(tradesSummary([{ live_net: null }] as PaperTradeOut[])).toBe('1 open · —')
    expect(tradesSummary([])).toBe('None open')
  })

  it('chart: the last close', () => {
    expect(chartSummary([{ c: 1 }, { c: 24801.5 }] as CandleOut[])).toBe('last 24,801.50')
    expect(chartSummary([])).toBe('—')
  })

  it('evidence: the bias the rows add up to', () => {
    expect(evidenceSummary({ bias: 0.4213 } as BiasOut)).toBe('bias +0.421')
    expect(evidenceSummary(undefined)).toBe('—')
  })

  it('signal history: how many fired today on this index', () => {
    const all = [signal(), signal({ id: 's2' }), signal({ id: 's3', index: 'BANKNIFTY' })]
    expect(historySummary(all, 'NIFTY')).toBe('2 today')
  })

  it('option chain: PCR and max pain', () => {
    expect(chainSummary({ pcr: 1.024, max_pain: 24800 } as ChainOut)).toBe(
      'PCR 1.02 · max pain 24800',
    )
    expect(chainSummary({ pcr: null, max_pain: null } as ChainOut)).toBe('PCR — · max pain —')
    expect(chainSummary(undefined)).toBe('—')
  })
})
