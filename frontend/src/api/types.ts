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

export type Frame = HelloFrame | TickFrame | HealthFrame | PongFrame | ChainFrame

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
