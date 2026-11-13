import { act, renderHook } from '@testing-library/react'

import { NONE_MINIMISED, PANELS_KEY, parsePanels, useOpenOnNew, usePanels } from './panels'

describe('parsePanels', () => {
  it('reads stored minimised flags, treating anything missing as not minimised', () => {
    expect(parsePanels({ chart: true, evidence: false, bogus: true })).toEqual({
      ...NONE_MINIMISED,
      chart: true,
    })
  })

  it('falls back to nothing minimised for anything that is not a stored value', () => {
    for (const bad of [undefined, null, 'x', 3, [true]]) {
      expect(parsePanels(bad)).toEqual(NONE_MINIMISED)
    }
  })

  it('with nothing stored, keeps the option chain hidden if E1 had it hidden', () => {
    expect(parsePanels(undefined, false).chain).toBe(true)
    expect(parsePanels(undefined, true).chain).toBe(false)
    // a stored value wins over the old key
    expect(parsePanels({ chain: false }, false).chain).toBe(false)
  })
})

describe('usePanels', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with every panel normal', () => {
    const { result } = renderHook(() => usePanels())
    expect(result.current.minimised).toEqual(NONE_MINIMISED)
    expect(result.current.changed).toBe(false)
    expect(result.current.minimised.chart).toBe(false)
  })

  it('minimises and expands a panel, and remembers it', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.toggleMinimise('chart')
    })
    expect(result.current.minimised.chart).toBe(true)
    expect(result.current.changed).toBe(true)
    expect(renderHook(() => usePanels()).result.current.minimised.chart).toBe(true)
    act(() => {
      result.current.toggleMinimise('chart')
    })
    expect(result.current.minimised.chart).toBe(false)
  })

  it('open() expands a minimised panel and leaves others alone', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.toggleMinimise('signal')
    })
    act(() => {
      result.current.toggleMinimise('chart')
    })
    act(() => {
      result.current.open('signal')
    })
    expect(result.current.minimised.signal).toBe(false)
    expect(result.current.minimised.chart).toBe(true)
  })

  it('two panels opened in the same moment both open', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.toggleMinimise('signal')
      result.current.toggleMinimise('trades')
    })
    expect(result.current.minimised.signal).toBe(true)
    expect(result.current.minimised.trades).toBe(true)
    act(() => {
      result.current.open('signal')
      result.current.open('trades')
    })
    expect(result.current.minimised.signal).toBe(false)
    expect(result.current.minimised.trades).toBe(false)
  })

  it('restoreAll expands everything', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.toggleMinimise('bias')
    })
    act(() => {
      result.current.restoreAll()
    })
    expect(result.current.minimised).toEqual(NONE_MINIMISED)
    expect(result.current.changed).toBe(false)
  })

  it('honours the option chain hidden under E1 until a panel state is stored', () => {
    localStorage.setItem('tradedisha.chainOpen', 'false')
    const { result } = renderHook(() => usePanels())
    expect(result.current.minimised.chain).toBe(true)
    act(() => {
      result.current.toggleMinimise('chain')
    })
    expect(JSON.parse(localStorage.getItem(PANELS_KEY) ?? '{}')).toMatchObject({ chain: false })
    expect(renderHook(() => usePanels()).result.current.minimised.chain).toBe(false)
  })
})

describe('useOpenOnNew', () => {
  it('opens once for each id it has not seen, and not again for the same one', () => {
    const open = vi.fn()
    const { rerender } = renderHook(
      ({ ids }) => {
        useOpenOnNew(ids, open)
      },
      {
        initialProps: { ids: [] as string[] },
      },
    )
    expect(open).not.toHaveBeenCalled()

    rerender({ ids: ['s1'] })
    expect(open).toHaveBeenCalledTimes(1)

    // the same signal on a later render (say, after the trader minimised the card again)
    rerender({ ids: ['s1'] })
    expect(open).toHaveBeenCalledTimes(1)

    rerender({ ids: [] })
    rerender({ ids: ['s2'] })
    expect(open).toHaveBeenCalledTimes(2)

    // an id seen earlier coming back is not new
    rerender({ ids: ['s1', 's2'] })
    expect(open).toHaveBeenCalledTimes(2)
  })

  it('opens for an id already present on the first render', () => {
    const open = vi.fn()
    renderHook(() => {
      useOpenOnNew(['s1'], open)
    })
    expect(open).toHaveBeenCalledTimes(1)
  })
})
