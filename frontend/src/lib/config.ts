import type { ParameterField, ParamValues } from '../api/types'

/** Config values as text, keyed by path ("bias.entry_threshold"): what the editor edits. */
export type Draft = Record<string, string>

const TIME = /^(\d{2}:\d{2}):00$/

function text(v: unknown): string {
  if (typeof v === 'string') return TIME.exec(v)?.[1] ?? v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return JSON.stringify(v)
}

/** Every value in a config as text by its path; times lose their ":00" seconds. */
export function flatten(params: ParamValues): Draft {
  const out: Draft = {}
  const walk = (node: unknown, prefix: string) => {
    if (typeof node === 'object' && node !== null && !Array.isArray(node)) {
      for (const [k, v] of Object.entries(node)) walk(v, prefix ? `${prefix}.${k}` : k)
    } else {
      out[prefix] = text(node)
    }
  }
  walk(params, '')
  return out
}

function same(a: string | undefined, b: string | undefined): boolean {
  if (a === undefined || b === undefined) return false
  const [x, y] = [a.trim(), b.trim()]
  if (x === y) return true
  return x !== '' && y !== '' && Number(x) === Number(y)
}

/** The paths at which two configs differ, in the order of `a` and then what only `b` has. */
export function changedPaths(a: Draft, b: Draft): string[] {
  const paths = [...Object.keys(a), ...Object.keys(b).filter((p) => !(p in a))]
  return paths.filter((p) => !same(a[p], b[p]))
}

/**
 * The draft put back into the nested shape the API takes, on a copy of `base`. Numbers
 * become numbers; text that is not one is sent as typed so the server names the field.
 */
export function toValues(base: ParamValues, fields: ParameterField[], draft: Draft): ParamValues {
  const out = JSON.parse(JSON.stringify(base)) as ParamValues
  for (const f of fields) {
    const raw = draft[f.path]
    if (raw === undefined) continue
    const typed = raw.trim()
    const numeric = f.kind === 'number' || f.kind === 'integer'
    const value = numeric && typed !== '' && Number.isFinite(Number(typed)) ? Number(typed) : typed
    const keys = f.path.split('.')
    const last = keys.pop()
    let node: Record<string, unknown> = out
    for (const k of keys) {
      const next = node[k]
      if (typeof next !== 'object' || next === null) break
      node = next as Record<string, unknown>
    }
    if (last !== undefined) node[last] = value
  }
  return out
}

/** "0 to 1", "more than 0", "at least 2": the limits of a field, for its help line. */
export function limitsText(f: ParameterField): string | null {
  const lo =
    f.ge != null ? `at least ${String(f.ge)}` : f.gt != null ? `more than ${String(f.gt)}` : null
  const hi =
    f.le != null ? `at most ${String(f.le)}` : f.lt != null ? `less than ${String(f.lt)}` : null
  if (f.ge != null && f.le != null) return `${String(f.ge)} to ${String(f.le)}`
  return [lo, hi].filter(Boolean).join(', ') || null
}
