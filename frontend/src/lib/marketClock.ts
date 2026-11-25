import { useNow } from './useNow'

/**
 * The server's market clock, as seen from the browser: every frame carries `t_mkt`, the
 * market time it was sent at. Live, that is the wall clock (the server is local); in replay
 * it is the recorded day's, so signal countdowns, time held and the feed's age read as
 * they did on the day (spec §14). Headlines and latency stay on the wall clock.
 *
 * The offset is a module variable, not store state: it shifts by a few milliseconds with
 * every frame, and nothing should re-render for that. Readers pick it up on their own tick.
 */
let offset = 0

/** Re-base on a frame: `tMkt` is the market time it was sent at, `recvAt` when it arrived. */
export function syncMarketClock(tMkt: number | undefined, recvAt: number): void {
  if (tMkt !== undefined) offset = tMkt - recvAt
}

/** The market time now, epoch ms. */
export function marketNow(wall: number = Date.now()): number {
  return wall + offset
}

/** `useNow`, on the market clock: for anything compared with market timestamps. */
export function useMarketNow(everyMs = 500): number {
  return marketNow(useNow(everyMs))
}

/** For tests: back to the wall clock. */
export function resetMarketClock(): void {
  offset = 0
}
