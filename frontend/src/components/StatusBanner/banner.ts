import type { BannerOut, BullionStatusOut, HealthResponse } from '../../api/types'
import { fmtIstTime } from '../../lib/format'
import type { WsState } from '../../state/store'

export interface Banner {
  level: 'info' | 'error'
  /** a short heading, shown in bold before the text (the market's session state) */
  title?: string
  text: string
  /** true when what is on screen is last-known data, not live */
  stale: boolean
  /** offer the Upstox login */
  login: boolean
}

function fromServer(b: BannerOut): Banner {
  const since = b.since_ms == null ? '' : ` from ${fmtIstTime(b.since_ms)}`
  switch (b.code) {
    case 'login_missing':
      return {
        level: 'error',
        text: 'Login required. Sign in to Upstox to start the live feed.',
        stale: true,
        login: true,
      }
    case 'login_expired':
      return {
        level: 'error',
        text: 'Upstox login has expired (it ends at 03:30 IST every day). Sign in again to resume. What you see is the last known data.',
        stale: true,
        login: true,
      }
    case 'feed_not_started':
      return {
        level: 'error',
        text: 'The feed did not start. Check the backend log, then sign in again or restart.',
        stale: true,
        login: false,
      }
    case 'feed_gap':
      return {
        level: 'error',
        text: `Feed is not delivering prices. Showing the last known data${since}. No new signals; paper trades cannot be opened or closed until it returns.`,
        stale: true,
        login: false,
      }
    case 'holiday':
      return {
        level: 'info',
        title: 'NSE holiday',
        text: 'No trading today (holiday or weekend). Showing the last known data.',
        stale: false,
        login: false,
      }
    case 'pre_open':
      return {
        level: 'info',
        title: 'NSE pre-open',
        text: 'Signals start at 09:15 IST.',
        stale: false,
        login: false,
      }
    case 'market_closed':
      return {
        level: 'info',
        title: 'NSE market closed',
        text: 'Trading hours are 09:15 to 15:30 IST. Prices are the last known; no new signals until the next session.',
        stale: false,
        login: false,
      }
  }
}

function fromBullion(b: BullionStatusOut): Banner | null {
  switch (b.status) {
    case 'live':
      return null
    case 'stale': {
      const since = b.since_ms == null ? '' : ` from ${fmtIstTime(b.since_ms)}`
      return {
        level: 'error',
        text: `Bullion prices are not updating${since}. Showing the last known MCX prices.`,
        stale: true,
        login: false,
      }
    }
    case 'closed':
      return {
        level: 'info',
        title: 'MCX closed',
        text: 'Showing the last known bullion prices.',
        stale: false,
        login: false,
      }
    case 'holiday':
      return {
        level: 'info',
        title: 'MCX holiday',
        text: 'No MCX trading today (holiday or weekend). Showing the last known bullion prices.',
        stale: false,
        login: false,
      }
  }
}

/**
 * The single most important reason the screen is not live, or null.
 *
 * The BULLION tab follows MCX hours, so there the NSE session banners give way to the
 * bullion one. Login and connection problems still come first, and an index outage is
 * still shown, without dimming bullion prices that are live.
 */
export function currentBanner(
  health: HealthResponse | null,
  ws: WsState,
  onBullion = false,
): Banner | null {
  if (ws === 'closed') {
    return {
      level: 'error',
      text: 'Lost connection to the TradeDisha backend. Retrying. What you see is the last known data.',
      stale: true,
      login: false,
    }
  }
  const server = health?.banner ? fromServer(health.banner) : null
  if (!onBullion || !health?.bullion) return server
  if (server?.login || health.banner?.code === 'feed_not_started') return server
  const bullion = fromBullion(health.bullion)
  if (bullion?.level === 'error') return bullion
  if (server && health.banner?.code === 'feed_gap') return { ...server, stale: false }
  return bullion
}
