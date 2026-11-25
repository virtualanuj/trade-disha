import { postClientLatency } from '../api/client'

/** frames waiting for one paint; far more than a paint ever has, so only a safety cap */
const MAX_PENDING = 1000

/**
 * Collects browser-side latency samples and posts a summary once a minute.
 * out_to_recv: backend send → browser receive. recv_to_paint: receive → next animation frame.
 *
 * One animation-frame callback measures every frame received since the last paint, so a
 * burst of frames queues one callback, not one each. A hidden tab paints nothing, so no
 * paint is sampled while hidden: otherwise the callbacks pile up for as long as the tab is
 * in the background, then all run at once and each reports minutes of "paint" time.
 */
export class ClientLatency {
  private outToRecv: number[] = []
  private recvToPaint: number[] = []
  /** receive times of frames not yet painted */
  private pending: number[] = []
  private scheduled = false
  private timer: ReturnType<typeof setInterval> | null = null

  /** Latest per-hop samples for the debug overlay. */
  latest = { out_to_recv: 0, recv_to_paint: 0 }

  private readonly onVisibility = () => {
    if (document.hidden) this.pending = [] // they would be measured on the tab's return
  }

  start() {
    if (this.timer) return
    this.timer = setInterval(() => {
      void this.flush()
    }, 60_000)
    document.addEventListener('visibilitychange', this.onVisibility)
  }

  stop() {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    document.removeEventListener('visibilitychange', this.onVisibility)
  }

  recordFrame(tOut: number, tRecv: number) {
    const d = tRecv - tOut
    if (d >= 0 && d < 60_000) {
      this.outToRecv.push(d)
      this.latest.out_to_recv = d
    }
    if (document.hidden || this.pending.length >= MAX_PENDING) return
    this.pending.push(tRecv)
    if (this.scheduled) return
    this.scheduled = true
    requestAnimationFrame(() => {
      this.scheduled = false
      const paintedAt = Date.now()
      for (const recv of this.pending) {
        const p = paintedAt - recv
        this.recvToPaint.push(p)
        this.latest.recv_to_paint = p
      }
      this.pending = []
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
