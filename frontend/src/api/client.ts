import type {
  HealthResponse,
  JournalOut,
  MetricsResponse,
  PaperTradeOut,
  ParametersOut,
} from './types'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, signal ? { signal } : undefined)
  if (!res.ok) {
    throw new Error(`${path} ${String(res.status)}`)
  }
  return (await res.json()) as T
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health', signal)
}

export function fetchMetrics(signal?: AbortSignal): Promise<MetricsResponse> {
  return getJson<MetricsResponse>('/api/metrics', signal)
}

export async function postClientLatency(body: {
  out_to_recv_ms: number[]
  recv_to_paint_ms: number[]
}): Promise<void> {
  await fetch('/api/metrics/client', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    keepalive: true,
  })
}

export interface ReloadError {
  field: string
  message: string
}

export class ReloadFailed extends Error {
  constructor(public readonly errors: ReloadError[]) {
    super('config invalid')
  }
}

export async function reloadParameters(): Promise<ParametersOut> {
  const res = await fetch('/api/parameters/reload', { method: 'POST' })
  if (res.status === 422) {
    const body = (await res.json()) as { detail: ReloadError[] }
    throw new ReloadFailed(body.detail)
  }
  if (!res.ok) {
    throw new Error(`reload ${String(res.status)}`)
  }
  return (await res.json()) as ParametersOut
}

/** The server refused; `message` is its reason, fit to show the trader. */
export class Refused extends Error {}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    ...(body === undefined
      ? {}
      : { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }),
  })
  if (!res.ok) {
    let reason = `request failed (${String(res.status)})`
    try {
      const data = (await res.json()) as { detail?: unknown }
      if (typeof data.detail === 'string') reason = data.detail
    } catch {
      // keep the generic reason
    }
    throw new Refused(reason)
  }
  return (await res.json()) as T
}

export function openPaperTrade(signalId: string): Promise<PaperTradeOut> {
  return postJson<PaperTradeOut>('/api/paper-trades', { signal_id: signalId })
}

export function closePaperTrade(tradeId: string): Promise<PaperTradeOut> {
  return postJson<PaperTradeOut>(`/api/paper-trades/${encodeURIComponent(tradeId)}/close`)
}

export interface JournalQuery {
  index?: string
  from?: string
  to?: string
}

function query(q: JournalQuery): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(q)) {
    if (typeof v === 'string' && v) params.set(k, v)
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export function fetchPaperTrades(q: JournalQuery, signal?: AbortSignal): Promise<PaperTradeOut[]> {
  return getJson<PaperTradeOut[]>(`/api/paper-trades${query(q)}`, signal)
}

export function fetchJournal(q: JournalQuery, signal?: AbortSignal): Promise<JournalOut> {
  return getJson<JournalOut>(`/api/journal/stats${query(q)}`, signal)
}
