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
