import { renderHook } from '@testing-library/react'

import type { NewsOut } from '../api/types'
import { NEWS_SEEN_KEY, useNewsSeen } from './useNewsSeen'

const news = (...ts: number[]): NewsOut => ({
  status: 'ok',
  error: null,
  fetched_at: 1,
  stock_indices: {},
  items: ts.map((t) => ({
    heading: `h${String(t)}`,
    summary: null,
    link: null,
    published_ts: t,
    symbols: [],
  })),
})

const stored = () => JSON.parse(localStorage.getItem(NEWS_SEEN_KEY) ?? 'null') as unknown

describe('useNewsSeen', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('first visit: nothing is new, and the newest headline is recorded as seen', () => {
    const { result } = renderHook(() => useNewsSeen(news(30, 20), true))
    expect(result.current).toBeNull()
    expect(stored()).toBe(30)
  })

  it('while visible, keeps the baseline from when it opened so new ones keep their dot', () => {
    localStorage.setItem(NEWS_SEEN_KEY, '20')
    const { result, rerender } = renderHook(({ n }) => useNewsSeen(n, true), {
      initialProps: { n: news(30, 20) },
    })
    expect(result.current).toBe(20)
    expect(stored()).toBe(30)
    rerender({ n: news(40, 30, 20) })
    expect(result.current).toBe(20)
    expect(stored()).toBe(40)
  })

  it('not visible: reports the stored value and records nothing', () => {
    localStorage.setItem(NEWS_SEEN_KEY, '20')
    const { result } = renderHook(() => useNewsSeen(news(30, 20), false))
    expect(result.current).toBe(20)
    expect(stored()).toBe(20)
  })

  it('opening again moves the baseline to what was seen last time', () => {
    localStorage.setItem(NEWS_SEEN_KEY, '20')
    const { result, rerender } = renderHook(({ v, n }) => useNewsSeen(n, v), {
      initialProps: { v: true, n: news(30, 20) },
    })
    expect(result.current).toBe(20)
    rerender({ v: false, n: news(50, 30, 20) })
    expect(result.current).toBe(30) // minimised: 50 is new
    rerender({ v: true, n: news(50, 30, 20) })
    expect(result.current).toBe(30) // opened: 50 keeps its dot
    expect(stored()).toBe(50)
  })

  it('ignores a damaged stored value', () => {
    localStorage.setItem(NEWS_SEEN_KEY, '"soon"')
    const { result } = renderHook(() => useNewsSeen(news(30), false))
    expect(result.current).toBeNull()
  })
})
