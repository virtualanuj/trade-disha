import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { HeadlineOut, NewsOut } from '../../api/types'
import { Headlines } from './Headlines'

/** a row works out each chip's kind when it renders: counting those counts row renders */
const chips = vi.hoisted(() => ({ n: 0 }))
vi.mock('../../lib/news', async (load) => {
  const real = await load<typeof import('../../lib/news')>()
  return {
    ...real,
    chipKind: (...args: Parameters<typeof real.chipKind>) => {
      chips.n++
      return real.chipKind(...args)
    },
  }
})

// 17/11/2026 10:00 IST, and a headline from 09:30
const NOW = Date.UTC(2026, 10, 17, 4, 30)
const AT_0930 = Date.UTC(2026, 10, 17, 4, 0)
const MINUTE = 60_000

const news: NewsOut = {
  status: 'ok',
  error: null,
  fetched_at: NOW,
  items: [1, 2, 3].map((i) => ({
    heading: `H${String(i)}`,
    summary: null,
    link: `https://upstox.com/news/${String(i)}`,
    published_ts: AT_0930,
    symbols: ['SBIN'],
  })) satisfies HeadlineOut[],
  stock_indices: { SBIN: ['NIFTY', 'BANKNIFTY'] },
}

describe('Headlines and the clock', () => {
  it('re-renders no row while the clock moves within its band', () => {
    const view = render(<Headlines news={news} seenTs={null} now={NOW} />)
    const before = chips.n
    for (let i = 1; i <= 20; i++) {
      view.rerender(<Headlines news={news} seenTs={null} now={NOW + i * 500} />)
    }
    expect(chips.n).toBe(before)
  })

  it('re-renders the rows whose band changes, and shows the new band', () => {
    const view = render(<Headlines news={news} seenTs={null} now={NOW} />)
    expect(screen.getAllByTestId('headline')[0]).toHaveAttribute('data-fresh', 'hour')
    const before = chips.n
    view.rerender(<Headlines news={news} seenTs={null} now={AT_0930 + 61 * MINUTE} />)
    expect(chips.n).toBe(before + 3) // one chip each, three rows
    expect(screen.getAllByTestId('headline')[0]).toHaveAttribute('data-fresh', 'today')
  })
})
