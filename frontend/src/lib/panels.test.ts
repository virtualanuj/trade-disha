import { act, renderHook } from '@testing-library/react'

import {
  DEFAULT_ORDER,
  NEWS_HIDDEN_KEY,
  NONE_MINIMISED,
  ORDER_KEY,
  PANELS_KEY,
  moveUnit,
  parseOrder,
  parsePanels,
  unitOf,
  useOpenOnNew,
  usePanels,
} from './panels'

describe('parsePanels', () => {
  it('reads stored minimised flags, treating anything missing as not minimised', () => {
    expect(parsePanels({ chart: true, bias: true, bogus: true })).toEqual({
      ...NONE_MINIMISED,
      chart: true,
      bias: true,
    })
  })

  it('ignores the evidence flag: evidence is part of Market view since E9', () => {
    expect(parsePanels({ evidence: true })).toEqual(NONE_MINIMISED)
    expect(Object.keys(NONE_MINIMISED)).not.toContain('evidence')
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

describe('panel order', () => {
  it('every panel moves on its own; the option chain is not movable', () => {
    expect(unitOf('bias')).toBe('bias')
    expect(unitOf('signal')).toBe('signal')
    expect(unitOf('chart')).toBe('chart')
    expect(unitOf('chain')).toBeNull()
    expect(unitOf('news')).toBeNull()
  })

  it('starts with signal above market view', () => {
    expect(DEFAULT_ORDER).toEqual(['tiles', 'signal', 'bias', 'chart', 'trades', 'history'])
  })

  it('reads a stored order, dropping unknown and repeated ids and adding missing ones', () => {
    expect(parseOrder(['history', 'bogus', 'chart', 'history'])).toEqual([
      'history',
      'chart',
      'tiles',
      'signal',
      'bias',
      'trades',
    ])
  })

  it('carries an order stored before E9: the old pair becomes signal then market view', () => {
    expect(parseOrder(['tiles', 'chart', 'view', 'evidence', 'trades', 'history'])).toEqual([
      'tiles',
      'chart',
      'signal',
      'bias',
      'trades',
      'history',
    ])
    expect(parseOrder(['tiles', 'view', 'chart', 'evidence', 'trades', 'history'])).toBe(
      DEFAULT_ORDER,
    )
  })

  it('falls back to the default order for anything that is not a stored list', () => {
    for (const bad of [undefined, null, 'x', 3, { chart: 1 }]) {
      expect(parseOrder(bad)).toEqual(DEFAULT_ORDER)
    }
  })

  it('moves a unit one place and leaves the ends alone', () => {
    expect(moveUnit(DEFAULT_ORDER, 'chart', -1)).toEqual([
      'tiles',
      'signal',
      'chart',
      'bias',
      'trades',
      'history',
    ])
    expect(moveUnit(DEFAULT_ORDER, 'chart', 1).indexOf('chart')).toBe(4)
    expect(moveUnit(DEFAULT_ORDER, 'tiles', -1)).toBe(DEFAULT_ORDER)
    expect(moveUnit(DEFAULT_ORDER, 'history', 1)).toBe(DEFAULT_ORDER)
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

  it('a panel state stored before E10 leaves headlines expanded', () => {
    expect(parsePanels({ chain: true }).news).toBe(false)
    expect(NONE_MINIMISED.news).toBe(false)
  })

  it('hides and shows headlines, remembers it, and counts it as a change', () => {
    const { result } = renderHook(() => usePanels())
    expect(result.current.newsHidden).toBe(false)
    act(() => {
      result.current.setNewsHidden(true)
    })
    expect(result.current.newsHidden).toBe(true)
    expect(result.current.changed).toBe(true)
    expect(localStorage.getItem(NEWS_HIDDEN_KEY)).toBe('true')
    expect(renderHook(() => usePanels()).result.current.newsHidden).toBe(true)
    act(() => {
      result.current.setNewsHidden(false)
    })
    expect(result.current.newsHidden).toBe(false)
    expect(result.current.changed).toBe(false)
  })

  it('restoreAll shows hidden headlines again', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.setNewsHidden(true)
      result.current.toggleMinimise('news')
    })
    act(() => {
      result.current.restoreAll()
    })
    expect(result.current.newsHidden).toBe(false)
    expect(result.current.minimised.news).toBe(false)
    expect(result.current.changed).toBe(false)
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

  it('starts in the default order, with the ends unable to move outwards', () => {
    const { result } = renderHook(() => usePanels())
    expect(result.current.order).toEqual(DEFAULT_ORDER)
    expect(result.current.canMove('tiles', -1)).toBe(false)
    expect(result.current.canMove('tiles', 1)).toBe(true)
    expect(result.current.canMove('history', 1)).toBe(false)
    expect(result.current.canMove('chain', 1)).toBe(false)
  })

  it('moves a panel, and remembers the order', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.move('chart', -1)
    })
    expect(result.current.order.slice(0, 4)).toEqual(['tiles', 'signal', 'chart', 'bias'])
    expect(result.current.changed).toBe(true)
    expect(JSON.parse(localStorage.getItem(ORDER_KEY) ?? '[]')).toEqual(result.current.order)
    expect(renderHook(() => usePanels()).result.current.order).toEqual(result.current.order)
  })

  it('signal and market view move independently', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.move('signal', 1)
    })
    expect(result.current.order.slice(0, 3)).toEqual(['tiles', 'bias', 'signal'])
    act(() => {
      result.current.move('bias', 1)
    })
    expect(result.current.order).toEqual(DEFAULT_ORDER)
    expect(result.current.changed).toBe(false)
  })

  it('two moves in the same moment both land', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.move('history', -1)
      result.current.move('history', -1)
    })
    expect(result.current.order.indexOf('history')).toBe(3)
  })

  it('restoreAll puts the panels back in the default order', () => {
    const { result } = renderHook(() => usePanels())
    act(() => {
      result.current.move('trades', -1)
    })
    act(() => {
      result.current.restoreAll()
    })
    expect(result.current.order).toEqual(DEFAULT_ORDER)
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
