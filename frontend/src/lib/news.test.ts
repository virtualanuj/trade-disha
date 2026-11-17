import type { HeadlineOut, NewsOut } from '../api/types'
import {
  chipKind,
  dayLabel,
  fmtNewsTime,
  freshness,
  groupByDay,
  newCount,
  newestTs,
  newsSummary,
  safeLink,
} from './news'

// 17/11/2026 10:00 IST
const NOW = Date.UTC(2026, 10, 17, 4, 30)

const item = (published_ts: number, heading = 'H'): HeadlineOut => ({
  heading,
  summary: null,
  link: null,
  published_ts,
  symbols: ['SBIN'],
})

const news = (items: HeadlineOut[], over: Partial<NewsOut> = {}): NewsOut => ({
  status: 'ok',
  error: null,
  fetched_at: NOW,
  items,
  stock_indices: {},
  ...over,
})

describe('fmtNewsTime', () => {
  it('shows only the time for today, in IST', () => {
    expect(fmtNewsTime(Date.UTC(2026, 10, 17, 3, 50), NOW)).toBe('09:20')
    expect(fmtNewsTime(Date.UTC(2026, 10, 16, 18, 31), NOW)).toBe('00:01') // 00:01 IST on the 17th
  })

  it('adds DD/MM for an earlier day', () => {
    expect(fmtNewsTime(Date.UTC(2026, 10, 16, 10, 28), NOW)).toBe('16/11 15:58')
    expect(fmtNewsTime(Date.UTC(2026, 10, 16, 18, 29), NOW)).toBe('16/11 23:59')
  })
})

describe('safeLink', () => {
  it('keeps http and https links', () => {
    expect(safeLink('https://upstox.com/news/x')).toBe('https://upstox.com/news/x')
    expect(safeLink('http://example.com/a')).toBe('http://example.com/a')
  })

  it('drops anything else', () => {
    expect(safeLink('javascript:alert(1)')).toBeNull()
    expect(safeLink('data:text/html,hi')).toBeNull()
    expect(safeLink('/relative')).toBeNull()
    expect(safeLink('not a url')).toBeNull()
    expect(safeLink(null)).toBeNull()
  })
})

describe('newCount and newestTs', () => {
  it('counts headlines newer than the newest one seen', () => {
    const n = news([item(30), item(20), item(10)])
    expect(newCount(n, 15)).toBe(2)
    expect(newCount(n, 30)).toBe(0)
    expect(newestTs(n)).toBe(30)
  })

  it('counts nothing on a first visit or without news', () => {
    expect(newCount(news([item(30)]), null)).toBe(0)
    expect(newCount(null, 5)).toBe(0)
    expect(newestTs(null)).toBeNull()
    expect(newestTs(news([]))).toBeNull()
  })
})

describe('newsSummary', () => {
  const at = Date.UTC(2026, 10, 17, 4, 0) // 09:30 IST

  it('is the new count and the newest headline', () => {
    const n = news([item(at, 'Market wrap'), item(at - 1)])
    expect(newsSummary(n, at - 5, NOW)).toBe('2 new · 09:30 Market wrap')
    expect(newsSummary(n, at, NOW)).toBe('09:30 Market wrap')
  })

  it('says why there is nothing to show', () => {
    expect(newsSummary(null, null, NOW)).toBe('Loading headlines')
    expect(newsSummary(news([], { status: 'needs_login' }), null, NOW)).toBe(
      'News needs the Upstox login',
    )
    expect(newsSummary(news([], { status: 'loading' }), null, NOW)).toBe('Loading headlines')
    expect(newsSummary(news([]), null, NOW)).toBe('No headlines in the last 7 days')
    expect(newsSummary(news([], { status: 'error', error: 'HTTP 500' }), null, NOW)).toBe(
      'Headlines unavailable: HTTP 500',
    )
  })
})

describe('days and freshness', () => {
  const MIN = 60_000

  it('names the IST day: Today, Yesterday, then weekday and DD/MM', () => {
    expect(dayLabel(Date.UTC(2026, 10, 16, 18, 31), NOW)).toBe('Today') // 00:01 IST 17th
    expect(dayLabel(Date.UTC(2026, 10, 16, 18, 29), NOW)).toBe('Yesterday') // 23:59 IST 16th
    expect(dayLabel(Date.UTC(2026, 10, 14, 6, 0), NOW)).toBe('Sat 14/11')
    expect(dayLabel(Date.UTC(2026, 10, 13, 6, 0), NOW)).toBe('Fri 13/11')
  })

  it('groups headlines by day in the order given, marking today', () => {
    const groups = groupByDay(
      [
        item(NOW - 5 * MIN, 'a'),
        item(NOW - 60 * MIN, 'b'),
        item(Date.UTC(2026, 10, 16, 10, 0), 'c'),
        item(Date.UTC(2026, 10, 13, 6, 0), 'd'),
      ],
      NOW,
    )
    expect(groups.map((g) => [g.label, g.today, g.items.map((h) => h.heading)])).toEqual([
      ['Today', true, ['a', 'b']],
      ['Yesterday', false, ['c']],
      ['Fri 13/11', false, ['d']],
    ])
    expect(groupByDay([], NOW)).toEqual([])
  })

  it('is hot within the hour, today after that, older before today', () => {
    expect(freshness(NOW - 59 * MIN, NOW)).toBe('hour')
    expect(freshness(NOW + MIN, NOW)).toBe('hour') // a clock a little ahead is still fresh
    expect(freshness(NOW - 61 * MIN, NOW)).toBe('today')
    expect(freshness(Date.UTC(2026, 10, 16, 18, 29), NOW)).toBe('older')
  })
})

describe('chipKind', () => {
  const indices = { SBIN: ['NIFTY', 'BANKNIFTY'], PNB: ['BANKNIFTY'], ITC: ['NIFTY'] }

  it('a bank chip for anything in BANK NIFTY, nifty for NIFTY only, other otherwise', () => {
    expect(chipKind('SBIN', indices)).toBe('bank')
    expect(chipKind('PNB', indices)).toBe('bank')
    expect(chipKind('ITC', indices)).toBe('nifty')
    expect(chipKind('XYZ', indices)).toBe('other')
  })
})
