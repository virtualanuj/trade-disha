import { act, render, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useNow } from './useNow'

describe('useNow', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(1_000_000)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('moves on every interval', () => {
    const { result } = renderHook(() => useNow(500))
    expect(result.current).toBe(1_000_000)
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current).toBe(1_000_500)
  })

  it('gives every reader the same moment, from one timer, in one render', () => {
    const seen: [number[], number[]] = [[], []]
    function Reader({ n }: { n: 0 | 1 }) {
      seen[n].push(useNow(500))
      return null
    }
    const spy = vi.spyOn(globalThis, 'setInterval')
    render(
      <>
        <Reader n={0} />
        <Reader n={1} />
      </>,
    )
    act(() => {
      vi.advanceTimersByTime(1_250)
    })
    expect(spy).toHaveBeenCalledTimes(1) // shared, not one per reader
    expect(seen[0]).toEqual(seen[1])
    expect(seen[0].at(-1)).toBe(1_001_000)
  })

  it('stops its timer when nothing reads it, and starts fresh for the next reader', () => {
    const first = renderHook(() => useNow(500))
    first.unmount()
    expect(vi.getTimerCount()).toBe(0)
    act(() => {
      vi.advanceTimersByTime(10_000)
    })
    const next = renderHook(() => useNow(500))
    expect(next.result.current).toBe(1_010_000) // not the moment the last reader left
    next.unmount()
  })

  it('keeps separate clocks for separate intervals', () => {
    const fast = renderHook(() => useNow(500))
    const slow = renderHook(() => useNow(5_000))
    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(fast.result.current).toBe(1_001_000)
    expect(slow.result.current).toBe(1_000_000)
    fast.unmount()
    slow.unmount()
  })
})
