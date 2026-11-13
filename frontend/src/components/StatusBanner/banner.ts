import type { BannerOut, HealthResponse } from '../../api/types'
import { fmtIstTime } from '../../lib/format'
import type { WsState } from '../../state/store'

export interface Banner {
  level: 'info' | 'error'
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
        text: 'Market holiday or weekend. Showing the last known data.',
        stale: false,
        login: false,
      }
    case 'pre_open':
      return {
        level: 'info',
        text: 'Pre-open session. Signals start at 09:15 IST.',
        stale: false,
        login: false,
      }
    case 'market_closed':
      return {
        level: 'info',
        text: 'Market closed. Showing the last known data.',
        stale: false,
        login: false,
      }
  }
}

/** The single most important reason the screen is not live, or null. */
export function currentBanner(health: HealthResponse | null, ws: WsState): Banner | null {
  if (ws === 'closed') {
    return {
      level: 'error',
      text: 'Lost connection to the TradeDisha backend. Retrying. What you see is the last known data.',
      stale: true,
      login: false,
    }
  }
  return health?.banner ? fromServer(health.banner) : null
}
