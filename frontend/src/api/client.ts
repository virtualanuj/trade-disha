import type { HealthResponse } from './types'

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch('/api/health', signal ? { signal } : undefined)
  if (!res.ok) {
    throw new Error(`health ${String(res.status)}`)
  }
  return (await res.json()) as HealthResponse
}
