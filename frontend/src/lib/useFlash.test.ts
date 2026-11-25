import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useFlash } from './useFlash'

type Flash = ReturnType<typeof useFlash>
interface Props {
  v: number | null
}

describe('useFlash', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('flashes up or down for 150 ms', () => {
    const { result, rerender } = renderHook<Flash, Props>(({ v }) => useFlash(v), {
      initialProps: { v: 100 },
    })
    expect(result.current).toBeNull()
    rerender({ v: 101 })
    expect(result.current).toBe('up')
    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(result.current).toBeNull()
    rerender({ v: 99 })
    expect(result.current).toBe('down')
  })

  it('does not stay lit when the value goes blank mid-flash', () => {
    const { result, rerender } = renderHook<Flash, Props>(({ v }) => useFlash(v), {
      initialProps: { v: 100 },
    })
    rerender({ v: 101 })
    expect(result.current).toBe('up')
    rerender({ v: null }) // a hello after a reconnect, within the 150 ms
    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(result.current).toBeNull()
  })
})
