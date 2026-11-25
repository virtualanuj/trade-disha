import type { ExitReason, FillQuality } from '../api/types'

/** How a paper trade ended, as the Journal and Trades pages word it. */
export const REASON_TEXT: Record<ExitReason, string> = {
  TARGET: 'Target',
  STOP: 'Stop',
  SQUARE_OFF: 'Square-off',
  MANUAL: 'Manual',
}

/** The badge for an exit that was not filled on a live price (spec §14). */
export const QUALITY_TEXT: Record<
  Exclude<FillQuality, 'live'>,
  { label: string; title: string }
> = {
  after_gap: {
    label: 'after gap',
    title: 'The feed was down; this exit used the first price after it came back.',
  },
  stale: {
    label: 'stale price',
    title: 'Squared off while the feed was down, at the last price the app had seen.',
  },
}
