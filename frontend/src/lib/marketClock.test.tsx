import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { countdown } from './format'
import { marketNow, resetMarketClock, syncMarketClock, useMarketNow } from './marketClock'

const WALL = 1_795_700_000_000 // 26/11/2026, in the browser
const REPLAYED = 1_795_180_000_000 // the recorded day the server is replaying

describe('market clock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(WALL)
    resetMarketClock()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('is the wall clock until a frame says otherwise (live: the server is local)', () => {
    expect(marketNow()).toBe(WALL)
    syncMarketClock(WALL - 3, WALL) // a live frame, 3 ms in transit
    expect(marketNow()).toBe(WALL - 3)
  })

  it('follows the replayed day, and moves on between frames', () => {
    syncMarketClock(REPLAYED, WALL)
    const { result } = renderHook(() => useMarketNow(500))
    expect(result.current).toBe(REPLAYED)
    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(result.current).toBe(REPLAYED + 1_000)
  })

  it('counts a replayed signal down from its TTL, not from 0:00', () => {
    const expiresAt = REPLAYED + 300_000 // fired at REPLAYED, 5-minute TTL
    syncMarketClock(REPLAYED, WALL)
    expect(countdown(expiresAt, marketNow())).toBe('5:00')
    expect(countdown(expiresAt, Date.now())).toBe('0:00') // what the page showed before
  })

  it('ignores a frame without a market time (an older server)', () => {
    syncMarketClock(REPLAYED, WALL)
    syncMarketClock(undefined, WALL + 10)
    expect(marketNow()).toBe(REPLAYED)
  })
})
