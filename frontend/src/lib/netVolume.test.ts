import { describe, expect, it } from 'vitest'

import type { CandleOut } from '../api/types'
import { netVolumeAt, netVolumeBars } from './netVolume'

const c = (t: number, v: number, bv: number | null, sv: number | null): CandleOut => ({
  t,
  o: 1,
  h: 1,
  l: 1,
  c: 1,
  v,
  synthetic: false,
  bv,
  sv,
})

describe('net volume', () => {
  it('gives one bar per minute with side data: buys minus sells', () => {
    const bars = netVolumeBars([c(1, 100, 60, 30), c(2, 50, 10, 40), c(3, 70, null, null)])
    expect(bars).toEqual([
      { time: 1, value: 30, buy: 60, sell: 30, unclassified: 10 },
      { time: 2, value: -30, buy: 10, sell: 40, unclassified: 0 },
    ])
  })

  it('reads the minute under the crosshair, or the latest', () => {
    const bars = netVolumeBars([c(1, 100, 60, 30), c(2, 50, 10, 40)])
    expect(netVolumeAt(bars, 1)?.value).toBe(30)
    expect(netVolumeAt(bars, null)?.value).toBe(-30)
    expect(netVolumeAt(bars, 9)).toBeUndefined()
    expect(netVolumeAt([], null)).toBeUndefined()
  })
})
