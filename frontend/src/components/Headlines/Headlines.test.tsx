import { fireEvent, render, screen, within } from '@testing-library/react'

import type { HeadlineOut, NewsOut } from '../../api/types'
import { Headlines } from './Headlines'

// 17/11/2026 10:00 IST
const NOW = Date.UTC(2026, 10, 17, 4, 30)
const TODAY_0930 = Date.UTC(2026, 10, 17, 4, 0)
const YESTERDAY_1558 = Date.UTC(2026, 10, 16, 10, 28)

const item = (over: Partial<HeadlineOut>): HeadlineOut => ({
  heading: 'H',
  summary: null,
  link: 'https://upstox.com/news/1',
  published_ts: TODAY_0930,
  symbols: ['SBIN'],
  ...over,
})

const news = (items: HeadlineOut[], over: Partial<NewsOut> = {}): NewsOut => ({
  status: 'ok',
  error: null,
  fetched_at: NOW,
  items,
  stock_indices: { SBIN: ['NIFTY', 'BANKNIFTY'], ITC: ['NIFTY'] },
  ...over,
})

describe('Headlines', () => {
  it('lists headlines in the order given, with times and symbol chips', () => {
    render(
      <Headlines
        news={news([
          item({ heading: 'Newer', symbols: ['ITC', 'BHARTIARTL'] }),
          item({ heading: 'Older', published_ts: YESTERDAY_1558, link: 'https://x/2' }),
        ])}
        seenTs={null}
        now={NOW}
      />,
    )
    const rows = screen.getAllByTestId('headline')
    expect(rows.map((r) => within(r).getByRole('link').textContent)).toEqual(['Newer', 'Older'])
    const [newer, older] = rows.map((r) => within(r))
    expect(newer?.getByText('09:30')).toBeInTheDocument()
    expect(older?.getByText('15:58')).toBeInTheDocument() // the day is in its group's header
    expect(newer?.getByText('ITC')).toBeInTheDocument()
    expect(newer?.getByText('BHARTIARTL')).toBeInTheDocument()
  })

  it('opens an http(s) article in a new tab', () => {
    render(<Headlines news={news([item({ heading: 'Wrap' })])} seenTs={null} now={NOW} />)
    const a = screen.getByRole('link', { name: 'Wrap' })
    expect(a).toHaveAttribute('href', 'https://upstox.com/news/1')
    expect(a).toHaveAttribute('target', '_blank')
    expect(a).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows a heading with an unsafe or missing link as plain text', () => {
    render(
      <Headlines
        news={news([
          item({ heading: 'Bad', link: 'javascript:alert(1)' }),
          item({ heading: 'None', link: null }),
        ])}
        seenTs={null}
        now={NOW}
      />,
    )
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText('Bad')).toBeInTheDocument()
    expect(screen.getByText('None')).toBeInTheDocument()
  })

  it('shows the summary only after a click', () => {
    render(
      <Headlines
        news={news([item({ heading: 'Wrap', summary: 'Nifty ended higher' })])}
        seenTs={null}
        now={NOW}
      />,
    )
    const toggle = screen.getByRole('button', { name: 'Show summary' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Nifty ended higher')).toBeNull()
    fireEvent.click(toggle)
    expect(screen.getByText('Nifty ended higher')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide summary' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('has no summary button without a summary', () => {
    render(<Headlines news={news([item({})])} seenTs={null} now={NOW} />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('marks headlines newer than the newest one seen', () => {
    render(
      <Headlines
        news={news([
          item({ heading: 'New', published_ts: TODAY_0930 }),
          item({ heading: 'Seen', published_ts: TODAY_0930 - 60_000, link: 'https://x/2' }),
        ])}
        seenTs={TODAY_0930 - 60_000}
        now={NOW}
      />,
    )
    const [first, second] = screen.getAllByTestId('headline')
    expect(first).toHaveAttribute('data-new', 'true')
    expect(second).not.toHaveAttribute('data-new')
  })

  it.each([
    [null, 'Loading headlines'],
    [news([], { status: 'needs_login' }), 'News needs the Upstox login'],
    [news([], { status: 'loading' }), 'Loading headlines'],
    [news([]), 'No headlines in the last 7 days'],
    [news([], { status: 'error', error: 'Upstox replied HTTP 500' }), 'Upstox replied HTTP 500'],
  ])('says why the list is empty (%#)', (n, text) => {
    render(<Headlines news={n} seenTs={null} now={NOW} />)
    expect(screen.getByText(text, { exact: false })).toBeInTheDocument()
  })

  it('keeps the last list under an error, with the error shown', () => {
    render(
      <Headlines
        news={news([item({ heading: 'Kept' })], {
          status: 'error',
          error: 'Upstox did not answer',
        })}
        seenTs={null}
        now={NOW}
      />,
    )
    expect(screen.getByText('Kept')).toBeInTheDocument()
    expect(screen.getByText(/Upstox did not answer/)).toBeInTheDocument()
  })

  it('keeps the last list after the login expires, with a note', () => {
    render(
      <Headlines
        news={news([item({ heading: 'Kept' })], { status: 'needs_login' })}
        seenTs={null}
        now={NOW}
      />,
    )
    expect(screen.getByText('Kept')).toBeInTheDocument()
    expect(screen.getByText(/News needs the Upstox login/)).toBeInTheDocument()
  })

  it('groups by day under headers, today first and earlier days muted', () => {
    render(
      <Headlines
        news={news([
          item({ heading: 'Now', link: 'https://x/1', published_ts: TODAY_0930 - 2 * 3_600_000 }),
          item({ heading: 'Then', published_ts: YESTERDAY_1558, link: 'https://x/2' }),
        ])}
        seenTs={null}
        now={NOW}
      />,
    )
    const groups = screen.getAllByTestId('headline-day')
    expect(groups.map((g) => g.getAttribute('data-day'))).toEqual(['Today', 'Yesterday'])
    const [today, yesterday] = groups.map((g) => within(g))
    expect(today?.getByText('Now')).toBeInTheDocument()
    expect(yesterday?.getByText('Then')).toBeInTheDocument()
    const [now, then] = screen.getAllByTestId('headline')
    expect(now).toHaveAttribute('data-fresh', 'today')
    expect(then).toHaveAttribute('data-fresh', 'older')
  })

  it('marks a headline from the last hour as hot', () => {
    render(
      <Headlines
        news={news([item({ published_ts: NOW - 10 * 60_000 })])}
        seenTs={null}
        now={NOW}
      />,
    )
    expect(screen.getByTestId('headline')).toHaveAttribute('data-fresh', 'hour')
  })

  it('colours each stock chip by its index', () => {
    render(
      <Headlines
        news={news([item({ symbols: ['SBIN', 'ITC', 'XYZ'] })])}
        seenTs={null}
        now={NOW}
      />,
    )
    expect(screen.getByText('SBIN')).toHaveAttribute('data-kind', 'bank')
    expect(screen.getByText('ITC')).toHaveAttribute('data-kind', 'nifty')
    expect(screen.getByText('XYZ')).toHaveAttribute('data-kind', 'other')
    expect(screen.getByText('SBIN')).toHaveAttribute('title', 'In NIFTY and BANK NIFTY')
  })
})
