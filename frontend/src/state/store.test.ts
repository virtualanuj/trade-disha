import type { FlowOut, SignalOut } from '../api/types'
import { useMarketStore } from './store'

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
