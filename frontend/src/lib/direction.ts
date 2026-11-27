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

/** The side of a trade in a word, for a neutral tag: a call or put bought, a future long or short. */
export function sideTag(d: SignalDirection): 'call' | 'put' | 'long' | 'short' {
  if (d === 'BUY_CE') return 'call'
  if (d === 'BUY_PE') return 'put'
  return d === 'BUY_FUT' ? 'long' : 'short'
}

/** The instrument without its side: "25300 CE", "FUT", or a mini's "GOLDM FUT". */
export function instrumentName(x: {
  direction: SignalDirection
  strike: number
  index?: string
  trading_symbol?: string
}): string {
  if (isFuture(x.direction)) {
    const contract = x.trading_symbol?.split(' ')[0]
    return contract && x.index && contract !== x.index ? `${contract} FUT` : 'FUT'
  }
  return instrumentLabel(x)
}

/**
 * "25300 CE", "25300 PE", "FUT long" or "FUT short"; a metal's mini names itself,
 * "GOLDM FUT long" (E28), when its symbol is not its metal's.
 */
export function instrumentLabel(x: {
  direction: SignalDirection
  strike: number
  index?: string
  trading_symbol?: string
}): string {
  if (isFuture(x.direction)) {
    const side = `FUT ${x.direction === 'BUY_FUT' ? 'long' : 'short'}`
    const contract = x.trading_symbol?.split(' ')[0]
    return contract && x.index && contract !== x.index ? `${contract} ${side}` : side
  }
  return `${String(x.strike)} ${x.direction === 'BUY_CE' ? 'CE' : 'PE'}`
}
