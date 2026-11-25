import type { BullionOut, IndexPrices, PaperTradeOut } from '../api/types'
import { trade } from '../components/OpenTrades/fixtures'
import { newestBullionTs, newestIndexTickTs, openTradeCount, tradeRevision } from './marketViews'

const price = (index: string, spot: number | null, fut: number | null): IndexPrices => ({
  index,
  spot_ltp: 1,
  spot_ts: spot,
  fut_ltp: 1,
  fut_ts: fut,
})

describe('market views', () => {
  it('finds the newest index tick across spot and future', () => {
    expect(newestIndexTickTs({})).toBeNull()
    expect(
      newestIndexTickTs({ NIFTY: price('NIFTY', 10, 30), BANKNIFTY: price('BANKNIFTY', 20, null) }),
    ).toBe(30)
  })

  it('finds the newest bullion tick', () => {
    const bullion = (stamps: (number | null)[]) =>
      ({ metals: stamps.map((updated_ts) => ({ updated_ts })) }) as unknown as BullionOut
    expect(newestBullionTs(null)).toBeNull()
    expect(newestBullionTs(bullion([null]))).toBeNull()
    expect(newestBullionTs(bullion([5, null, 9]))).toBe(9)
  })

  it('counts open trades, and moves the revision on each open and close', () => {
    const closed: PaperTradeOut = { ...trade, id: 'c', status: 'closed' }
    expect(openTradeCount([trade, closed])).toBe(1)
    const opened = tradeRevision([trade])
    const thenClosed = tradeRevision([{ ...trade, status: 'closed' }])
    const another = tradeRevision([
      { ...trade, status: 'closed' },
      { ...trade, id: 't2' },
    ])
    expect(new Set([0, opened, thenClosed, another]).size).toBe(4)
    expect(tradeRevision([{ ...trade, live_net: 999 }])).toBe(opened) // live P&L is no change
  })
})
