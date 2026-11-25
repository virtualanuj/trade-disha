import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClientLatency } from './latency'

const post = vi.hoisted(() => vi.fn<(body: unknown) => Promise<void>>(() => Promise.resolve()))
vi.mock('../api/client', () => ({ postClientLatency: post }))

/** requestAnimationFrame that runs only when the test says a frame is painted */
let queued: FrameRequestCallback[] = []
function paint(): void {
  const run = queued
  queued = []
  for (const cb of run) cb(performance.now())
}

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('ClientLatency', () => {
  let clock = 0
  beforeEach(() => {
    queued = []
    clock = 1_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => clock)
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      queued.push(cb)
      return queued.length
    })
    setHidden(false)
    post.mockClear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  async function flushed(l: ClientLatency) {
    await l.flush()
    return post.mock.calls.at(-1)?.[0] as
      { out_to_recv_ms: number[]; recv_to_paint_ms: number[] } | undefined
  }

  it('queues one animation frame however many frames arrive, and samples each frame', async () => {
    const l = new ClientLatency()
    l.start()
    l.recordFrame(clock - 5, clock) // received at 1_000_000
    clock += 4
    l.recordFrame(clock - 3, clock) // received at 1_000_004
    clock += 4
    l.recordFrame(clock - 2, clock) // received at 1_000_008
    expect(queued).toHaveLength(1)
    clock += 6 // painted at 1_000_014
    paint()
    const body = await flushed(l)
    expect(body?.out_to_recv_ms).toEqual([5, 3, 2])
    expect(body?.recv_to_paint_ms).toEqual([14, 10, 6])
    l.recordFrame(clock - 1, clock)
    expect(queued).toHaveLength(1) // the next paint gets a fresh callback
    l.stop()
  })

  it('samples no paint while the tab is hidden: a hidden tab paints nothing', async () => {
    const l = new ClientLatency()
    l.start()
    setHidden(true)
    for (let i = 0; i < 1000; i++) l.recordFrame(clock - 2, clock)
    expect(queued).toHaveLength(0)
    const body = await flushed(l)
    expect(body?.out_to_recv_ms).toHaveLength(1000) // the network hop is still measured
    expect(body?.recv_to_paint_ms).toEqual([])
    l.stop()
  })

  it('drops frames still waiting to paint when the tab is hidden', async () => {
    const l = new ClientLatency()
    l.start()
    l.recordFrame(clock - 2, clock)
    setHidden(true)
    clock += 600_000 // ten minutes in the background
    setHidden(false)
    paint() // the callback queued before hiding finally runs
    expect((await flushed(l))?.recv_to_paint_ms ?? []).toEqual([])
    l.recordFrame(clock - 2, clock)
    clock += 7
    paint()
    expect((await flushed(l))?.recv_to_paint_ms).toEqual([7])
    l.stop()
  })
})
