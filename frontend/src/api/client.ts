import type { HealthResponse, MetricsResponse } from './types'

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
