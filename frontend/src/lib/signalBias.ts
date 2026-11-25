import type { BiasOut, SignalOut } from '../api/types'
import { isLong } from './direction'

type Fired = Pick<
  SignalOut,
  'index' | 'minute_ts' | 'direction' | 'bias' | 'strength' | 'breakdown'
>

/**
 * The market view a signal fired on, rebuilt from the breakdown stored with it
 * (`engine/bias_engine.py:breakdown_json`), so `EvidenceTable` can show it again.
 * A signal only fires on its own side, so the label follows the direction.
 */
export function biasFromSignal(s: Fired): BiasOut {
  const b = s.breakdown
  return {
    index: s.index,
    minute_ts: s.minute_ts,
    bias: s.bias,
    label: isLong(s.direction) ? 'Bullish' : 'Bearish',
    strength: s.strength,
    is_expiry_day: b.is_expiry_day ?? false,
    group_scores: b.group_scores ?? {},
    group_weights: b.group_weights ?? {},
    indicators: b.indicators ?? [],
  }
}
