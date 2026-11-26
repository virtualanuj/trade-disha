import type {
  BankOut,
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
import { BULLION_TAB, useMarketStore } from './store'

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

  it('keeps the BULLION tab selected across a hello', () => {
    const s = useMarketStore.getState()
    s.selectIndex(BULLION_TAB)
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
    expect(after.selectedIndex).toBe(BULLION_TAB)
    expect(after.bullionCandles.GOLD).toHaveLength(1)
  })

  it('leaves the BULLION tab when there is no bullion', () => {
    const s = useMarketStore.getState()
    s.selectIndex(BULLION_TAB)
    s.applyBullion({ metals: [], ratio: null, etfs: [] })
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
