import { ETF_TAB } from '../state/store'
import { tabGroups, tabIds } from './tabs'

describe('tabGroups (E32)', () => {
  it('puts the indices and the ETFs on NSE, and each metal on MCX', () => {
    const groups = tabGroups(['NIFTY', 'BANKNIFTY'], true, ['GOLD', 'SILVER'])
    expect(groups).toEqual([
      {
        exchange: 'NSE',
        tabs: [
          { id: 'NIFTY', label: 'NIFTY' },
          { id: 'BANKNIFTY', label: 'BANKNIFTY' },
          { id: ETF_TAB, label: 'BULLION' },
        ],
      },
      {
        exchange: 'MCX',
        tabs: [
          { id: 'GOLD', label: 'GOLD' },
          { id: 'SILVER', label: 'SILVER' },
        ],
      },
    ])
    expect(tabIds(groups)).toEqual(['NIFTY', 'BANKNIFTY', ETF_TAB, 'GOLD', 'SILVER'])
  })

  it('leaves out what has no data: no ETF tab, no MCX group', () => {
    expect(tabGroups(['NIFTY', 'BANKNIFTY'], false, [])).toEqual([
      {
        exchange: 'NSE',
        tabs: [
          { id: 'NIFTY', label: 'NIFTY' },
          { id: 'BANKNIFTY', label: 'BANKNIFTY' },
        ],
      },
    ])
  })
})
