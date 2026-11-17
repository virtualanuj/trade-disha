import { useEffect, useState } from 'react'

import type { NewsOut } from '../api/types'
import { newestTs } from './news'
import { usePref } from './usePref'

/** time of the newest headline seen with the panel open, remembered in this browser */
export const NEWS_SEEN_KEY = 'tradedisha.newsSeen'

function parseSeen(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/**
 * The time headlines must be newer than to count as new (spec §13.2 Headlines).
 *
 * While the list is visible, the newest headline is recorded as seen, but the value
 * returned stays at what had been seen when the panel opened, so a headline that is new
 * keeps its dot until the panel is next opened. While not visible (minimised or hidden),
 * the recorded value is returned, for the "N new" count on the title bar.
 */
export function useNewsSeen(news: NewsOut | null, visible: boolean): number | null {
  const [seen, storeSeen] = usePref(NEWS_SEEN_KEY, parseSeen)
  const [wasVisible, setWasVisible] = useState(visible)
  const [baseline, setBaseline] = useState(seen)
  if (visible !== wasVisible) {
    setWasVisible(visible)
    if (visible) setBaseline(seen)
  }

  const newest = newestTs(news)
  useEffect(() => {
    if (visible && newest != null && (seen == null || newest > seen)) storeSeen(newest)
  }, [visible, newest, seen, storeSeen])

  return visible ? baseline : seen
}
