import type { ChartInterval } from '../api/types'

/** The chart's bar sizes (E27); the view and signals stay on 1-minute closes. */
export const CHART_INTERVALS: readonly ChartInterval[] = ['10s', '30s', '1m', '5m']

/** what a bar is, in words, for the chart's empty text and titles */
export const INTERVAL_TEXT: Record<ChartInterval, string> = {
  '10s': '10-second',
  '30s': '30-second',
  '1m': '1-minute',
  '5m': '5-minute',
}

export const INTERVAL_MS: Record<ChartInterval, number> = {
  '10s': 10_000,
  '30s': 30_000,
  '1m': 60_000,
  '5m': 300_000,
}

/** A stored interval back to a valid one; anything else is 1 m. */
export const asInterval = (v: unknown): ChartInterval =>
  CHART_INTERVALS.includes(v as ChartInterval) ? (v as ChartInterval) : '1m'
