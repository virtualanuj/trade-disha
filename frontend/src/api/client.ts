import type {
  ConfigVersionDetail,
  ConfigVersionOut,
  HealthResponse,
  JournalOut,
  MetricsResponse,
  PaperTradeOut,
  ParameterField,
  ParametersOut,
  ParamValues,
  PruneOut,
  UsageOut,
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

export interface ConfigError {
  /** a field path, a group ("weights"), "tag", or a marker such as "<params>" */
  field: string
  message: string
}

/** The server refused a config change; nothing was saved. */
export class ConfigRejected extends Error {
  constructor(public readonly errors: ConfigError[]) {
    super('config invalid')
  }
}

async function sendConfig(path: string, method: string, body: unknown): Promise<ParametersOut> {
  const res = await fetch(path, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (res.status === 422) {
    const detail = ((await res.json()) as { detail: unknown }).detail
    throw new ConfigRejected(
      Array.isArray(detail)
        ? detail.map((d: { field?: unknown; message?: unknown; loc?: unknown; msg?: unknown }) => ({
            field: typeof d.field === 'string' ? d.field : '<request>',
            message:
              typeof d.message === 'string' ? d.message : typeof d.msg === 'string' ? d.msg : '',
          }))
        : [{ field: '<request>', message: String(detail) }],
    )
  }
  if (!res.ok) {
    throw new Error(`${path} ${String(res.status)}`)
  }
  return (await res.json()) as ParametersOut
}

export function fetchParameterSchema(): Promise<ParameterField[]> {
  return getJson<ParameterField[]>('/api/parameters/schema')
}

/** Save edited values as a new config version; rejects with ConfigRejected if invalid. */
export function saveParameters(tag: string, params: ParamValues): Promise<ParametersOut> {
  return sendConfig('/api/parameters', 'PUT', { tag, params })
}

export function listConfigVersions(): Promise<ConfigVersionOut[]> {
  return getJson<ConfigVersionOut[]>('/api/parameters/versions')
}

const versionCache = new Map<number, Promise<ConfigVersionDetail>>()

/** One version with its values. A version never changes, so each is fetched once. */
export function getConfigVersion(version: number): Promise<ConfigVersionDetail> {
  let hit = versionCache.get(version)
  if (!hit) {
    hit = getJson<ConfigVersionDetail>(`/api/parameters/versions/${String(version)}`)
    versionCache.set(version, hit)
    hit.catch(() => versionCache.delete(version))
  }
  return hit
}

/** Put an old version's values back in force, as a new version. */
export function revertConfigVersion(version: number, tag?: string): Promise<ParametersOut> {
  return sendConfig(
    `/api/parameters/versions/${String(version)}/revert`,
    'POST',
    tag ? { tag } : {},
  )
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

export function fetchUsage(untilDate?: string, signal?: AbortSignal): Promise<UsageOut> {
  const q = untilDate ? `?until_date=${encodeURIComponent(untilDate)}` : ''
  return getJson<UsageOut>(`/api/data/usage${q}`, signal)
}

export function pruneTicks(untilDate: string): Promise<PruneOut> {
  return postJson<PruneOut>('/api/data/prune-ticks', { until_date: untilDate })
}

/** Switch one factor of an index's or metal's bias on or off: a new config version tagged
 * `Factor NIFTY.pcr: off`, from the next minute close (E16). */
export function setFactor(scope: string, name: string, enabled: boolean): Promise<ParametersOut> {
  return sendConfig(
    `/api/parameters/factors/${encodeURIComponent(scope)}/${encodeURIComponent(name)}`,
    'PUT',
    { enabled },
  )
}
