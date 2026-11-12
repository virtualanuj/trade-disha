import { clientLatency } from '../lib/latency'
import { useMarketStore } from '../state/store'
import type { Frame } from './types'

const MIN_BACKOFF = 500
const MAX_BACKOFF = 10_000

function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws`
}

/** Keeps one WebSocket open, with exponential reconnect, feeding the market store. */
export class MarketSocket {
  private socket: WebSocket | null = null
  private backoff = MIN_BACKOFF
  private stopped = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  start() {
    this.stopped = false
    this.connect()
    clientLatency.start()
  }

  stop() {
    this.stopped = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.socket?.close()
    this.socket = null
    clientLatency.stop()
  }

  private connect() {
    const store = useMarketStore.getState()
    store.setWs('connecting')
    const ws = new WebSocket(wsUrl())
    this.socket = ws

    ws.onopen = () => {
      this.backoff = MIN_BACKOFF
      useMarketStore.getState().setWs('open')
    }
    ws.onmessage = (ev: MessageEvent<string>) => {
      this.handle(JSON.parse(ev.data) as Frame)
    }
    ws.onclose = () => {
      useMarketStore.getState().setWs('closed')
      this.scheduleReconnect()
    }
    ws.onerror = () => {
      ws.close()
    }
  }

  private scheduleReconnect() {
    if (this.stopped) return
    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, this.backoff)
    this.backoff = Math.min(MAX_BACKOFF, this.backoff * 2)
  }

  private handle(frame: Frame) {
    const recvAt = Date.now()
    const s = useMarketStore.getState()
    switch (frame.type) {
      case 'hello':
        s.applyHello(frame.payload.health, frame.payload.instruments, frame.payload.prices)
        break
      case 'tick':
        clientLatency.recordFrame(frame.t_out, recvAt)
        s.applyTick(frame.payload, recvAt)
        break
      case 'health':
        s.applyHealth(frame.payload)
        break
      case 'pong':
        break
    }
  }
}
