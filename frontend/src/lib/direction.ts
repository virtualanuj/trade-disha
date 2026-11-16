import type { SignalDirection } from '../api/types'

/**
 * Index signals buy a call or a put; bullion signals buy or sell the MCX future
 * (spec §9a). "Long" is the side that gains when the price rises: a call or a bought future.
 */
export function isLong(d: SignalDirection): boolean {
  return d === 'BUY_CE' || d === 'BUY_FUT'
}

export function isFuture(d: SignalDirection): boolean {
  return d === 'BUY_FUT' || d === 'SELL_FUT'
}

export function directionLabel(d: SignalDirection): 'BUY' | 'SELL' {
  return d === 'SELL_FUT' ? 'SELL' : 'BUY'
}

/** "25300 CE", "25300 PE", "FUT long" or "FUT short". */
export function instrumentLabel(x: { direction: SignalDirection; strike: number }): string {
  if (isFuture(x.direction)) return `FUT ${x.direction === 'BUY_FUT' ? 'long' : 'short'}`
  return `${String(x.strike)} ${x.direction === 'BUY_CE' ? 'CE' : 'PE'}`
}
