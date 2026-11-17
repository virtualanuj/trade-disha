import type { HeadlineOut, NewsOut } from '../api/types'

const istDay = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})
const istDayMonth = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  day: '2-digit',
  month: '2-digit',
})
const istHourMinute = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

const istWeekday = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', weekday: 'short' })
const DAY_MS = 86_400_000
const HOUR_MS = 3_600_000

/** A headline's time, `HH:MM` (IST); the day is in its group's header. */
export function fmtNewsClock(ts: number): string {
  return istHourMinute.format(new Date(ts))
}

/** The IST day of `ts` as a header: Today, Yesterday, or `Fri 14/11`. */
export function dayLabel(ts: number, now: number): string {
  const day = istDay.format(new Date(ts))
  if (day === istDay.format(new Date(now))) return 'Today'
  if (day === istDay.format(new Date(now - DAY_MS))) return 'Yesterday'
  return `${istWeekday.format(new Date(ts))} ${istDayMonth.format(new Date(ts))}`
}

export interface DayGroup {
  label: string
  today: boolean
  items: HeadlineOut[]
}

/** Consecutive headlines of the same IST day, in the order given (newest first). */
export function groupByDay(items: HeadlineOut[], now: number): DayGroup[] {
  const groups: DayGroup[] = []
  for (const h of items) {
    const label = dayLabel(h.published_ts, now)
    const last = groups[groups.length - 1]
    if (last?.label === label) last.items.push(h)
    else groups.push({ label, today: label === 'Today', items: [h] })
  }
  return groups
}

/** How fresh a headline is: within the hour, earlier today, or an earlier day (IST). */
export type Freshness = 'hour' | 'today' | 'older'

export function freshness(ts: number, now: number): Freshness {
  if (now - ts < HOUR_MS) return 'hour'
  return dayLabel(ts, now) === 'Today' ? 'today' : 'older'
}

/** A stock chip's colour: in BANK NIFTY, in NIFTY only, or not known to be in either. */
export type ChipKind = 'bank' | 'nifty' | 'other'

export function chipKind(symbol: string, stockIndices: Record<string, string[]>): ChipKind {
  const indices = stockIndices[symbol] ?? []
  if (indices.includes('BANKNIFTY')) return 'bank'
  return indices.includes('NIFTY') ? 'nifty' : 'other'
}

/** A headline's time with its day: `HH:MM` today, `DD/MM HH:MM` before (IST). */
export function fmtNewsTime(ts: number, now: number): string {
  const time = istHourMinute.format(new Date(ts))
  if (istDay.format(new Date(ts)) === istDay.format(new Date(now))) return time
  return `${istDayMonth.format(new Date(ts))} ${time}`
}

/** The link if it is an absolute http(s) URL, otherwise null (shown as plain text). */
export function safeLink(link: string | null): string | null {
  if (link == null) return null
  try {
    const url = new URL(link)
    return url.protocol === 'http:' || url.protocol === 'https:' ? link : null
  } catch {
    return null
  }
}

/** Time of the newest headline, or null when there is none. */
export function newestTs(news: NewsOut | null): number | null {
  const first = news?.items[0]
  return first ? first.published_ts : null
}

/**
 * Headlines newer than the newest one the trader has seen. Nothing counts as new on a
 * first visit (`seenTs` null): a week of news is not a week of new news.
 */
export function newCount(news: NewsOut | null, seenTs: number | null): number {
  if (news == null || seenTs == null) return 0
  return news.items.filter((h) => h.published_ts > seenTs).length
}

/** Why the list is empty, or why it may be stale; null when there is nothing to say. */
export function newsStatusText(news: NewsOut | null): string | null {
  if (news == null || news.status === 'loading') return 'Loading headlines'
  if (news.status === 'needs_login') return 'News needs the Upstox login'
  if (news.status === 'error') return `Headlines unavailable: ${news.error ?? 'unknown error'}`
  return news.items.length === 0 ? 'No headlines in the last 7 days' : null
}

/** The one line on the minimised Headlines bar. */
export function newsSummary(news: NewsOut | null, seenTs: number | null, now: number): string {
  const first = news?.status === 'ok' ? news.items[0] : undefined
  if (news == null || first === undefined) return newsStatusText(news) ?? ''
  const fresh = newCount(news, seenTs)
  const head = `${fmtNewsTime(first.published_ts, now)} ${first.heading}`
  return fresh > 0 ? `${String(fresh)} new · ${head}` : head
}
