import type { ParamValues } from '../api/types'

/** Each factor's name on screen, by the name the backend gives it. */
export const FACTOR_LABEL: Record<string, string> = {
  ema_cross: 'EMA crossover',
  vwap_position: 'Futures vs VWAP',
  supertrend: 'Supertrend',
  pcr: 'Put-call ratio',
  oi_change_atm: 'ATM OI build-up',
  max_pain_drift: 'Max-pain drift',
  premium_momentum: 'CE vs PE momentum',
  iv_change: 'IV change',
  premium_confirmation: 'Premium confirmation',
  dollar_index: 'Dollar index (proxy)',
  usd_inr: 'USD/INR',
  crude: 'Crude oil',
  gold: 'Gold',
  silver: 'Silver',
  gift_nifty: 'GIFT Nifty gap',
  futures_oi: 'Futures OI build-up',
  net_volume: 'Net traded volume',
  book_imbalance: 'Order-book lean',
  peer_metal: 'Other metal’s trend',
}

/** The scopes with factor switches, as the engines name them and as `factors` keys them. */
export const FACTOR_SCOPES = [
  { scope: 'NIFTY', key: 'nifty', label: 'NIFTY' },
  { scope: 'BANKNIFTY', key: 'banknifty', label: 'BANK NIFTY' },
  { scope: 'GOLD', key: 'gold', label: 'GOLD' },
  { scope: 'SILVER', key: 'silver', label: 'SILVER' },
] as const

/** factor name -> 'on' | 'off' */
export type Switches = Record<string, string>

/** One index's or metal's switches in the config in force (E16); undefined if it has none. */
export function factorSwitches(
  params: ParamValues | undefined,
  scope: string,
): Switches | undefined {
  const key = FACTOR_SCOPES.find((s) => s.scope === scope)?.key
  const value = key ? params?.factors?.[key] : undefined
  return value && typeof value === 'object' ? (value as Switches) : undefined
}

export function offNames(switches: Switches | undefined): string[] {
  return Object.entries(switches ?? {})
    .filter(([, v]) => v === 'off')
    .map(([k]) => k)
}

/** One or two plain sentences on what each factor reads and which way it votes (docs/signal.md §3). */
export const FACTOR_HELP: Record<string, string> = {
  ema_cross:
    'Gap between the fast (9) and slow (21) EMA of spot closes. Fast above slow is bullish.',
  vwap_position:
    'Where the future trades against today’s VWAP. Above VWAP is bullish; 0.3 % away is full strength.',
  supertrend:
    'Which side of the Supertrend line spot is on. A fresh flip counts a third at first and grows over three bars.',
  pcr: 'Put-call ratio over ATM ± 5 strikes. Above 1 (more puts written) is read as bullish.',
  oi_change_atm:
    'Open-interest build-up in the calls and puts near ATM over the last minute, signed by whether premiums rose or fell.',
  max_pain_drift: 'How far the max-pain strike has moved in 15 minutes. Moving up is bullish.',
  premium_momentum:
    '5-minute change of the ATM call minus that of the ATM put. Calls outpacing puts is bullish.',
  iv_change:
    'Rising implied volatility, in the direction spot is moving. Falling IV does not vote.',
  premium_confirmation:
    'Whether option premiums back the 5-minute spot move. A divergence pulls against the move.',
  dollar_index:
    'A dollar-index proxy from NSE currency futures. A stronger dollar is bearish for Indian indices.',
  usd_inr: 'The USD/INR future. A weaker rupee is bearish.',
  crude: 'MCX crude oil. Rising crude is bearish: a bigger import bill and inflation.',
  gold: 'MCX gold. Money moving into gold is read as risk-off, so bearish.',
  silver: 'MCX silver. Shown for information only; it carries no weight.',
  gift_nifty:
    'GIFT Nifty’s overnight move (NIFTY only). Votes with or against the gap at the open and fades out over the first 30 minutes.',
  futures_oi:
    'Open-interest build-up in the metal’s future, signed by the price move: long build-up is bullish, short build-up bearish.',
  net_volume: 'Volume traded at the ask minus volume at the bid. Buyers lifting offers is bullish.',
  book_imbalance: 'Which way the order book leans: more bids than offers is bullish.',
  peer_metal: 'The trend of the other metal (silver for gold, gold for silver), read as support.',
}
