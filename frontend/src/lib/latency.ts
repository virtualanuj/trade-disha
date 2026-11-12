import { postClientLatency } from '../api/client'

/**
 * Collects browser-side latency samples and posts a summary once a minute.
 * out_to_recv: backend send → browser receive. recv_to_paint: receive → next animation frame.
 */
class ClientLatency {
  private outToRecv: number[] = []
  private recvToPaint: number[] = []
  private timer: ReturnType<typeof setInterval> | null = null

  /** Latest per-hop samples for the debug overlay. */
  latest = { out_to_recv: 0, recv_to_paint: 0 }

  start() {
    if (this.timer) return
    this.timer = setInterval(() => {
      void this.flush()
    }, 60_000)
  }

  stop() {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  recordFrame(tOut: number, tRecv: number) {
    const d = tRecv - tOut
    if (d >= 0 && d < 60_000) {
      this.outToRecv.push(d)
      this.latest.out_to_recv = d
    }
    requestAnimationFrame(() => {
      const p = Date.now() - tRecv
      this.recvToPaint.push(p)
      this.latest.recv_to_paint = p
    })
  }

  async flush() {
    if (!this.outToRecv.length && !this.recvToPaint.length) return
    const body = { out_to_recv_ms: this.outToRecv, recv_to_paint_ms: this.recvToPaint }
    this.outToRecv = []
    this.recvToPaint = []
    try {
      await postClientLatency(body)
    } catch {
      // metrics are best-effort
    }
  }
}

export const clientLatency = new ClientLatency()
