import type { BullionOut, IndexPrices, IndexStatsOut, QuoteOut } from '../api/types'
import { stripRates } from './rates'

const nifty: IndexPrices = {
  index: 'NIFTY',
  spot_ltp: 24_512.3,
  spot_ts: 1,
  fut_ltp: 24_560,
  fut_ts: 1,
}
const niftyStats = { index: 'NIFTY', prev_close: 24_409.9 } as IndexStatsOut
const sensex: QuoteOut = {
  name: 'SENSEX',
  ltp: 80_911.05,
  prev_close: 80_605.95,
  change: 305.1,
  change_pct: 0.38,
  updated_ts: 1,
}
const bullion = {
  metals: [
    { metal: 'GOLD', ltp: 134_914, change_pct: -1.31 },
    { metal: 'SILVER', ltp: 170_115, change_pct: 0.2 },
  ],
  ratio: 79.31,
  etfs: [
    { metal: 'SILVER', symbol: 'SILVERBEES', ltp: 150.1, change_pct: 0.31 },
    { metal: 'GOLD', symbol: 'GOLDBEES', ltp: 108.42, change_pct: 0.57 },
  ],
} as unknown as BullionOut

describe('stripRates', () => {
  it('lists the six rates in order, each with its change and where a click goes', () => {
    const got = stripRates(nifty, niftyStats, [sensex], bullion, ['NIFTY', 'BANKNIFTY', 'BULLION'])
    expect(got).toEqual([
      { name: 'NIFTY', ltp: 24_512.3, changePct: 0.42, metal: null, tab: 'NIFTY' },
      { name: 'SENSEX', ltp: 80_911.05, changePct: 0.38, metal: null, tab: null },
      { name: 'GOLD', ltp: 134_914, changePct: -1.31, metal: 'GOLD', tab: 'BULLION' },
      { name: 'SILVER', ltp: 170_115, changePct: 0.2, metal: 'SILVER', tab: 'BULLION' },
      { name: 'GOLDBEES', ltp: 108.42, changePct: 0.57, metal: 'GOLD', tab: 'BULLION' },
      { name: 'SILVERBEES', ltp: 150.1, changePct: 0.31, metal: 'SILVER', tab: 'BULLION' },
    ])
  })

  it('keeps every entry with nothing known, and offers no BULLION tab without bullion', () => {
    const got = stripRates(undefined, undefined, [], null, ['NIFTY', 'BANKNIFTY'])
    expect(got.map((r) => r.name)).toEqual([
      'NIFTY',
      'SENSEX',
      'GOLD',
      'SILVER',
      'GOLDBEES',
      'SILVERBEES',
    ])
    expect(got.every((r) => r.ltp == null && r.changePct == null)).toBe(true)
    expect(got.map((r) => r.tab)).toEqual(['NIFTY', null, null, null, null, null])
  })

  it('has no NIFTY change before the previous close is known', () => {
    const [n] = stripRates(nifty, undefined, [], null, ['NIFTY'])
    expect(n).toMatchObject({ ltp: 24_512.3, changePct: null })
  })
})
