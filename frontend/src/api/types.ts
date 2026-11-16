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

export type BannerCode =
  | 'login_missing'
  | 'login_expired'
  | 'feed_not_started'
  | 'feed_gap'
  | 'market_closed'
  | 'holiday'
  | 'pre_open'

export interface BannerOut {
  code: BannerCode
  level: 'info' | 'error'
  since_ms: number | null
}

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
  /** connected and a tick arrived within the last few seconds */
  feed_live: boolean
  /** why the screen is not live; null when all is well */
  banner: BannerOut | null
  serves_frontend: boolean
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
    flow: FlowOut[]
    paper_trades: PaperTradeOut[]
    stats: IndexStatsOut[]
  }
}

/** Order-flow score for an index and its parts, each -1 (selling) to +1 (buying). */
export interface FlowOut {
  index: string
  ts: number
  /** null when no part has data */
  score: number | null
  fut_book: number | null
  fut_trades: number | null
  options: number | null
  /** true when signals fire on it; false while it is only recorded (shadow) */
  live: boolean
}

export interface FlowFrame extends FrameBase {
  type: 'flow'
  payload: FlowOut
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
  | PaperTradeFrame
  | StatsFrame
  | FlowFrame

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

export type ParamValues = Record<string, Record<string, unknown>>

/** The config in force: a numbered, tagged version of the tunable parameters. */
export interface ParametersOut {
  version: number
  tag: string
  created_ts: number
  params: ParamValues
}

/** One editable value, as `GET /api/parameters/schema` describes it. */
export interface ParameterField {
  /** "bias.entry_threshold", "signal.expiry_points.NIFTY.target" */
  path: string
  group: string
  /** the path without its group */
  key: string
  kind: 'number' | 'integer' | 'choice' | 'time'
  help: string
  ge: number | null
  gt: number | null
  le: number | null
  lt: number | null
  choices: string[] | null
}

export interface ConfigVersionOut {
  version: number
  tag: string
  created_ts: number
  source: 'seed' | 'edit' | 'revert'
  reverted_from: number | null
  active: boolean
}

export interface ConfigVersionDetail extends ConfigVersionOut {
  /** as stored; an old version may not have today's fields */
  params: ParamValues
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
  /** best ask when it fired, and the bid-ask spread then as % of the mid price */
  entry_ask: number | null
  spread_pct: number | null
  /** the rule that fired it */
  entry_mode: 'minute_close' | 'trigger'
  /** fired by the rule that is not live: scored for comparison, never tradable */
  shadow: boolean
  flow_score: number | null
  /** the config version in force when it fired; null for signals from before versions */
  config_version: number | null
  /** null for signals fired before outcomes were scored */
  outcome: OutcomeOut | null
}

export type OutcomeResult = 'open' | 'target' | 'stop' | 'neither'

/** What the option did after the signal fired, traded or not. */
export interface OutcomeOut {
  result: OutcomeResult
  result_ts: number | null
  end_ts: number
  best_price: number
  best_ts: number
  /** over the signal's entry price */
  best_pct: number
  worst_price: number
  worst_ts: number
  worst_pct: number
  px_1m: number | null
  px_5m: number | null
  px_15m: number | null
  spot_pre_move: number | null
  spot_best_move: number | null
  /** share of the favourable spot move already over at firing: 0 early, 1 late */
  late_share: number | null
  final: boolean
}

export type GateReason =
  | 'below_threshold'
  | 'active_exists'
  | 'outside_hours'
  | 'feed_down'
  | 'no_price'
  | 'rearm'
  | 'no_setup'
  | 'flow_not_confirmed'
  | 'spread_wide'

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

export type ExitReason = 'TARGET' | 'STOP' | 'SQUARE_OFF' | 'MANUAL'
export type FillQuality = 'live' | 'after_gap' | 'stale'

export interface PaperTradeOut {
  id: string
  signal_id: string
  index: string
  instrument_key: string
  trading_symbol: string
  direction: SignalDirection
  strike: number
  expiry: string
  lots: number
  qty: number
  signal_entry: number
  entry_price: number
  entry_ts: number
  /** fill minus the signal's entry price */
  slippage: number
  target_price: number
  stop_price: number
  /** round-trip cost for the whole trade */
  cost: number
  status: 'open' | 'closed'
  exit_price: number | null
  exit_ts: number | null
  exit_reason: ExitReason | null
  exit_fill_quality: FillQuality | null
  exit_price_age_ms: number | null
  gross: number | null
  net: number | null
  warning: 'bias_reversed' | null
  /** live view while open */
  ltp: number | null
  ltp_ts: number | null
  live_gross: number | null
  live_net: number | null
}

export interface PaperTradeFrame extends FrameBase {
  type: 'paper_trade'
  payload: { trades: PaperTradeOut[] }
}

export interface JournalStatsOut {
  /** "overall" or an index name */
  scope: string
  trades: number
  hits: number
  hit_rate: number | null
  avg_win: number | null
  avg_loss: number | null
  net_total: number
  gross_total: number
  avg_duration_s: number | null
  by_reason: Partial<Record<ExitReason, number>>
  non_live_fills: number
}

export interface JournalOut {
  stats: JournalStatsOut[]
  open_trades: number
}

export interface UsageOut {
  db_bytes: number
  tick_rows: number
  tick_days: number
  oldest: string | null
  newest: string | null
  prune_rows: number
  prune_days: number
  prune_bytes_estimate: number
}

export interface PruneOut {
  until_date: string
  rows_deleted: number
  bytes_freed: number
}

/** Day statistics for the index details view. A null means the feed has no source for it. */
export interface IndexStatsOut {
  index: string
  day_open: number | null
  day_high: number | null
  day_low: number | null
  /** 0 at the day's low, 1 at the day's high */
  range_pos: number | null
  prev_close: number | null
  change: number | null
  change_pct: number | null
  high_52w: number | null
  low_52w: number | null
  /** futures price minus spot */
  fut_premium: number | null
  vix: number | null
  vix_change_pct: number | null
  updated_ts: number | null
}

export interface StatsFrame extends FrameBase {
  type: 'stats'
  payload: IndexStatsOut
}
