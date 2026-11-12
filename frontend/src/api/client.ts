import type { HealthResponse, MetricsResponse, ParametersOut } from './types'

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
