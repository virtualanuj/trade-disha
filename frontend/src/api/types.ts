export interface FeedHealth {
  state: 'connecting' | 'connected' | 'disconnected'
  last_tick_ts: number | null
  tick_age_ms: number | null
  reconnects: number
  subscribed: number
  provider: string
}

export type MarketStatus = 'pre_open' | 'live' | 'closed' | 'holiday'
export type AuthState = 'missing' | 'valid' | 'expired' | 'not_required'

export interface HealthResponse {
  status: string
  app: string
  version: string
  milestone: number
  market_status: MarketStatus
  now_ms: number
  auth: AuthState
  feed: FeedHealth
  replay_day: string | null
}

export interface InstrumentOut {
  instrument_key: string
  trading_symbol: string
  instrument_type: 'INDEX' | 'FUT' | 'CE' | 'PE'
  expiry: string | null
  strike: number | null
  lot_size: number
}

export interface StrikePairOut {
  strike: number
  ce: InstrumentOut
  pe: InstrumentOut
}

export interface ResolvedIndexOut {
  index: string
  spot: InstrumentOut
  future: InstrumentOut
  options_expiry: string
  is_expiry_day: boolean
  strike_step: number
  atm: number
  lot_size: number
  strikes: StrikePairOut[]
}

export interface IndexPrices {
  index: string
  spot_ltp: number | null
  spot_ts: number | null
  fut_ltp: number | null
  fut_ts: number | null
}

export interface HopOut {
  hop: string
  n: number
  p50: number
  p95: number
  p99: number
  max: number
}

export interface MetricsResponse {
  last_1m: HopOut[]
  last_15m: HopOut[]
}

interface FrameBase {
  ts: number
  t_src: number | null
  t_in: number | null
  t_out: number
}

export interface HelloFrame extends FrameBase {
  type: 'hello'
  payload: {
    health: HealthResponse
    instruments: ResolvedIndexOut[]
    prices: IndexPrices[]
    chains: ChainOut[]
    candles: CandlesResponse[]
    bias: BiasOut[]
    parameters: ParametersOut
    signals_active: SignalOut[]
    signals_today: SignalOut[]
    gates: GateOut[]
  }
}

export interface TickFrame extends FrameBase {
  type: 'tick'
  payload: IndexPrices
}

export interface HealthFrame extends FrameBase {
  type: 'health'
  payload: HealthResponse
}

export interface PongFrame extends FrameBase {
  type: 'pong'
  payload: null
}

export type Frame =
  | HelloFrame
  | TickFrame
  | HealthFrame
  | PongFrame
  | ChainFrame
  | CandleFrame
  | BiasFrame
  | ParametersFrame
  | SignalFrame

export type BuildUp =
  'long_buildup' | 'short_buildup' | 'short_covering' | 'long_unwinding' | 'none'

export interface LegOut {
  ltp: number | null
  chg_pct: number | null
  oi: number | null
  oi_chg_open: number | null
  oi_chg_min: number | null
  iv: number | null
  buildup: BuildUp
}

export interface ChainRowOut {
  strike: number
  ce: LegOut
  pe: LegOut
}

export interface ChainOut {
  index: string
  expiry: string
  step: number
  atm: number
  spot: number | null
  pcr: number | null
  max_pain: number | null
  total_ce_oi: number
  total_pe_oi: number
  oi_baseline: 'session_open' | 'partial'
  max_abs_oi_chg: number
  updated_ts: number | null
  rows: ChainRowOut[]
}

export interface ChainFrame extends FrameBase {
  type: 'chain'
  payload: ChainOut
}

export interface CandleOut {
  t: number
  o: number
  h: number
  l: number
  c: number
  v: number
  synthetic: boolean
}

export interface OverlayOut {
  t: number
  ema_fast: number | null
  ema_slow: number | null
  vwap: number | null
  supertrend: number | null
  supertrend_dir: number
}

export interface CandlesResponse {
  index: string
  spot_key: string
  candles: CandleOut[]
  overlays: OverlayOut[]
}

export interface IndicatorOut {
  name: string
  group: 'trend' | 'oi' | 'premium'
  score: number
  note: string
  quality: 'ok' | 'warming' | 'partial'
  value: Record<string, number>
  weight: number
  contribution: number
}

export interface BiasOut {
  index: string
  minute_ts: number
  bias: number
  label: 'Bullish' | 'Neutral' | 'Bearish'
  strength: number
  is_expiry_day: boolean
  group_scores: Record<string, number>
  group_weights: Record<string, number>
  indicators: IndicatorOut[]
}

export interface ParametersOut {
  loaded_at: number
  path: string
  params: Record<string, Record<string, unknown>>
}

export interface CandleFrame extends FrameBase {
  type: 'candle'
  payload: { index: string; role: 'spot' | 'fut'; candle: CandleOut }
}

export interface BiasFrame extends FrameBase {
  type: 'bias'
  payload: { bias: BiasOut; overlay: OverlayOut; gates: GateOut[] }
}

export interface ParametersFrame extends FrameBase {
  type: 'parameters'
  payload: ParametersOut & { effective_from_minute_ts: number }
}

export type SignalStatus = 'active' | 'traded' | 'lapsed' | 'reversed'
export type SignalDirection = 'BUY_CE' | 'BUY_PE'

export interface SignalOut {
  id: string
  index: string
  minute_ts: number
  ts_fired: number
  direction: SignalDirection
  instrument_key: string
  trading_symbol: string
  strike: number
  expiry: string
  lot_size: number
  entry_price: number
  target_price: number
  stop_price: number
  target_basis: 'pct' | 'points'
  target_points: number | null
  stop_points: number | null
  delta_used: number | null
  bias: number
  strength: number
  breakdown: { indicators?: IndicatorOut[]; group_scores?: Record<string, number> }
  expires_at: number
  status: SignalStatus
  status_ts: number
}

export type GateReason =
  'below_threshold' | 'active_exists' | 'outside_hours' | 'feed_down' | 'no_price' | 'rearm'

export interface GateOut {
  index: string
  minute_ts: number
  fired: boolean
  reason: GateReason | null
}

export interface SignalFrame extends FrameBase {
  type: 'signal'
  payload: { signal: SignalOut; gates: GateOut[] }
}
