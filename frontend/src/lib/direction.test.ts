import { describe, expect, it } from 'vitest'

import { directionLabel, instrumentLabel, isLong } from './direction'

describe('direction', () => {
  it('treats a bought call and a bought future as long, a put and a short as not', () => {
    expect(isLong('BUY_CE')).toBe(true)
    expect(isLong('BUY_FUT')).toBe(true)
    expect(isLong('BUY_PE')).toBe(false)
    expect(isLong('SELL_FUT')).toBe(false)
  })

  it('names the action and the instrument', () => {
    expect(directionLabel('BUY_CE')).toBe('BUY')
    expect(directionLabel('SELL_FUT')).toBe('SELL')
    expect(instrumentLabel({ direction: 'BUY_PE', strike: 25300 })).toBe('25300 PE')
    expect(instrumentLabel({ direction: 'BUY_CE', strike: 25300 })).toBe('25300 CE')
    expect(instrumentLabel({ direction: 'SELL_FUT', strike: 0 })).toBe('FUT short')
    expect(instrumentLabel({ direction: 'BUY_FUT', strike: 0 })).toBe('FUT long')
  })
})
