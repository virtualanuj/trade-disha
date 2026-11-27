import type {
  BankOut,
  BullionEtfOut,
  BullionMetalOut,
  CandleOut,
  FlowOut,
  HealthResponse,
  NewsOut,
  OverlayOut,
  ParametersOut,
  ResolvedIndexOut,
  SignalOut,
} from '../api/types'
import { ETF_TAB, chartKey, useMarketStore } from './store'

const sig = (over: Partial<SignalOut>): SignalOut =>
  ({
    id: 's1',
    index: 'NIFTY',
    ts_fired: 1000,
    status: 'active',
    shadow: false,
    ...over,
  }) as SignalOut

describe('market store', () => {
  beforeEach(() => {
    useMarketStore.setState({ signals: {}, signalHistory: [], flow: {} })
  })

  it('never makes a shadow signal the active one, but keeps it in the history', () => {
    const { applySignal } = useMarketStore.getState()
    applySignal(sig({ id: 'live' }), [])
    applySignal(sig({ id: 'shadow', shadow: true, ts_fired: 2000 }), [])

    const s = useMarketStore.getState()
    expect(s.signals.NIFTY?.id).toBe('live')
    expect(s.signalHistory.map((x) => x.id)).toEqual(['shadow', 'live'])
  })

  it('a shadow signal ending does not clear the live one', () => {
    const { applySignal } = useMarketStore.getState()
    applySignal(sig({ id: 'live' }), [])
    applySignal(sig({ id: 'shadow', shadow: true, status: 'lapsed' }), [])

    expect(useMarketStore.getState().signals.NIFTY?.id).toBe('live')
  })

  it('refreshes the live levels of the waiting signal, and only that one', () => {
    const { applySignal, applySignalLive } = useMarketStore.getState()
    applySignal(sig({ id: 'a', live: null }), [])
    applySignalLive([
      sig({ id: 'a', live: { ltp: 160, target: 208, stop: 136 } }),
      sig({ id: 'gone', index: 'BANKNIFTY', live: { ltp: 1, target: 2, stop: 0.5 } }),
    ])
    const s = useMarketStore.getState()
    expect(s.signals.NIFTY?.live).toEqual({ ltp: 160, target: 208, stop: 136 })
    expect(s.signals.BANKNIFTY).toBeUndefined() // never brings back a signal that has ended
    expect(s.signalHistory[0]?.live).toBeNull() // history keeps what it had
  })

  it('keeps the latest order-flow reading per index', () => {
    const flow = { index: 'NIFTY', score: 0.2 } as FlowOut
    useMarketStore.getState().applyFlow(flow)
    useMarketStore.getState().applyFlow({ ...flow, index: 'BANKNIFTY' })
    useMarketStore.getState().applyFlow({ ...flow, score: 0.5 })

    const s = useMarketStore.getState()
    expect(s.flow.NIFTY?.score).toBe(0.5)
    expect(s.flow.BANKNIFTY?.score).toBe(0.2)
  })
})

describe('futures candles for net volume', () => {
  it('keeps the futures candles from frames, apart from the spot ones', () => {
    useMarketStore.setState({ candles: {}, futCandles: {} })
    const { applyCandle } = useMarketStore.getState()
    const k = (t: number) => ({ t, o: 1, h: 1, l: 1, c: 1, v: 5, synthetic: false, bv: 3, sv: 2 })
    applyCandle('NIFTY', 'spot', k(1))
    applyCandle('NIFTY', 'fut', k(1))
    applyCandle('NIFTY', 'fut', k(2))
    const s = useMarketStore.getState()
    expect(s.candles.NIFTY?.map((x) => x.t)).toEqual([1])
    expect(s.futCandles.NIFTY?.map((x) => x.t)).toEqual([1, 2])
  })
})

describe('bullion in the store', () => {
  const metal = { metal: 'GOLD' } as BullionMetalOut

  beforeEach(() => {
    useMarketStore.setState({
      selectedIndex: 'NIFTY',
      instruments: [{ index: 'NIFTY' } as ResolvedIndexOut],
      bullion: null,
      bullionCandles: {},
      bullionOverlays: {},
    })
  })

  it('keeps a metal tab selected across a hello', () => {
    const s = useMarketStore.getState()
    s.selectIndex('GOLD')
    s.applyHello(
      {} as HealthResponse,
      [{ index: 'NIFTY' } as ResolvedIndexOut],
      [],
      [],
      [],
      [],
      {} as ParametersOut,
      [],
      [],
      [],
      [],
      [],
      [],
    )
    s.applyBullion({ metals: [metal], ratio: null, etfs: [] }, [
      { metal: 'GOLD', candles: [{ t: 1 } as CandleOut], overlays: [] },
    ])
    const after = useMarketStore.getState()
    expect(after.selectedIndex).toBe('GOLD')
    expect(after.bullionCandles.GOLD).toHaveLength(1)
  })

  it('leaves a metal tab when that metal is not loaded (E32)', () => {
    const s = useMarketStore.getState()
    s.selectIndex('SILVER')
    s.applyBullion({ metals: [metal], ratio: null, etfs: [] })
    expect(useMarketStore.getState().selectedIndex).toBe('NIFTY')
  })

  it('keeps the NSE bullion tab while there are ETFs, and leaves it without (E32)', () => {
    const s = useMarketStore.getState()
    s.selectIndex(ETF_TAB)
    s.applyBullion({ metals: [], ratio: null, etfs: [{ metal: 'GOLD' } as BullionEtfOut] })
    expect(useMarketStore.getState().selectedIndex).toBe(ETF_TAB)
    s.applyBullion({ metals: [metal], ratio: null, etfs: [] })
    expect(useMarketStore.getState().selectedIndex).toBe('NIFTY')
  })

  it('adds closed candles, replacing one for the same minute', () => {
    const s = useMarketStore.getState()
    const c = (t: number, close: number) => ({ t, c: close }) as CandleOut
    const o = (t: number) => ({ t, vwap: 1 }) as OverlayOut
    s.applyBullionCandle('GOLD', c(1, 10), o(1))
    s.applyBullionCandle('GOLD', c(1, 11), o(1))
    s.applyBullionCandle('GOLD', c(2, 12), o(2))
    expect(useMarketStore.getState().bullionCandles.GOLD?.map((x) => x.c)).toEqual([11, 12])
  })

  it('keeps the latest headlines as sent', () => {
    const news: NewsOut = {
      status: 'ok',
      error: null,
      fetched_at: 5,
      stock_indices: {},
      items: [{ heading: 'H', summary: null, link: null, published_ts: 1, symbols: ['SBIN'] }],
    }
    useMarketStore.getState().applyNews(news)
    expect(useMarketStore.getState().news).toBe(news)
  })

  it('keeps the latest paper bank from a bank frame', () => {
    const bank = { opening_balance: 100, available: 100, blocked: 0 } as BankOut
    useMarketStore.getState().applyBank(bank)
    expect(useMarketStore.getState().bank).toBe(bank)
    const after = { ...bank, available: 40, blocked: 60 }
    useMarketStore.getState().applyBank(after)
    expect(useMarketStore.getState().bank?.available).toBe(40)
  })
})

describe('the chart at other intervals (E27)', () => {
  const bar = (t: number, c = 1) => ({
    t,
    o: c,
    h: c,
    l: c,
    c,
    v: 0,
    synthetic: false,
    bv: null,
    sv: null,
  })
  const line = (t: number) => ({
    t,
    ema_fast: 1,
    ema_slow: null,
    vwap: null,
    supertrend: null,
    supertrend_dir: 0,
  })
  const loaded = () => {
    useMarketStore.getState().loadChart({
      name: 'NIFTY',
      interval: '10s',
      candles: [bar(0), bar(10_000)],
      overlays: [line(0), line(10_000)],
      vol_candles: [bar(0)],
    })
  }
  const series = () => useMarketStore.getState().chartBars[chartKey('NIFTY', '10s')]

  it('ignores a bar for a chart not loaded', () => {
    useMarketStore.setState({ chartBars: {} })
    useMarketStore.getState().applyChartBar({
      name: 'NIFTY',
      interval: '10s',
      role: 'price',
      candle: bar(20_000),
      overlay: line(20_000),
    })
    expect(series()).toBeUndefined()
  })

  it('appends price bars with their line, and volume bars apart', () => {
    loaded()
    const s = useMarketStore.getState()
    s.applyChartBar({
      name: 'NIFTY',
      interval: '10s',
      role: 'price',
      candle: bar(20_000),
      overlay: line(20_000),
    })
    s.applyChartBar({
      name: 'NIFTY',
      interval: '10s',
      role: 'vol',
      candle: bar(10_000),
      overlay: null,
    })
    expect(series()?.candles.map((c) => c.t)).toEqual([0, 10_000, 20_000])
    expect(series()?.overlays.map((o) => o.t)).toEqual([0, 10_000, 20_000])
    expect(series()?.vol.map((c) => c.t)).toEqual([0, 10_000])
  })

  it('replaces a repeat of the last bar and drops an older one', () => {
    loaded()
    const s = useMarketStore.getState()
    s.applyChartBar({
      name: 'NIFTY',
      interval: '10s',
      role: 'price',
      candle: bar(10_000, 5),
      overlay: null,
    })
    s.applyChartBar({
      name: 'NIFTY',
      interval: '10s',
      role: 'price',
      candle: bar(0, 9),
      overlay: null,
    })
    expect(series()?.candles.map((c) => [c.t, c.c])).toEqual([
      [0, 1],
      [10_000, 5],
    ])
  })

  it('keeps each interval and chart apart', () => {
    loaded()
    useMarketStore.getState().applyChartBar({
      name: 'NIFTY',
      interval: '30s',
      role: 'price',
      candle: bar(30_000),
      overlay: null,
    })
    expect(useMarketStore.getState().chartBars[chartKey('NIFTY', '30s')]).toBeUndefined()
    expect(series()?.candles).toHaveLength(2)
  })
})
