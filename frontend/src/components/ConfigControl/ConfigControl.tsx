import { useEffect, useMemo, useRef, useState } from 'react'

import {
  ConfigRejected,
  fetchParameterSchema,
  listConfigVersions,
  revertConfigVersion,
  saveParameters,
  setFactor,
  type ConfigError,
} from '../../api/client'
import type { ConfigVersionOut, ParameterField, ParametersOut, ParamValues } from '../../api/types'
import { changedPaths, flatten, limitsText, toValues, type Draft } from '../../lib/config'
import {
  FACTOR_HELP,
  FACTOR_LABEL,
  FACTOR_SCOPES,
  factorSwitches,
  offNames,
} from '../../lib/factors'
import { fmtDate, fmtIstTime } from '../../lib/format'
import { useNow } from '../../lib/useNow'
import { FactorSwitch } from '../FactorSwitch/FactorSwitch'
import { toolClass } from '../../lib/toolbar'
import { ConfigIcon } from '../Icons/Icons'

export interface ConfigApi {
  schema: () => Promise<ParameterField[]>
  save: (tag: string, params: ParamValues) => Promise<ParametersOut>
  versions: () => Promise<ConfigVersionOut[]>
  revert: (version: number, tag?: string) => Promise<ParametersOut>
  /** one factor switch flipped: a new version with a fixed tag (E16) */
  setFactor: (scope: string, name: string, enabled: boolean) => Promise<ParametersOut>
}

const API: ConfigApi = {
  schema: fetchParameterSchema,
  save: saveParameters,
  versions: listConfigVersions,
  revert: revertConfigVersion,
  setFactor,
}

interface Props {
  parameters: ParametersOut | null
  effectiveFrom: number | null
  /** a save or revert went through: the new config and the minute it applies from */
  onSaved: (p: ParametersOut, effectiveFrom: number) => void
  api?: ConfigApi
}

const MAX_TAG = 60
const BOX = 'rounded border bg-bg px-1.5 py-0.5 text-fg focus:border-accent focus:outline-none'
const INPUT = `${BOX} w-28 shrink-0 text-right font-mono`
const TEXT = `${BOX} min-w-0 flex-1 border-border`
const BUTTON =
  'rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg disabled:opacity-50 disabled:hover:text-fg-muted'

function nextMinute(): number {
  return (Math.floor(Date.now() / 60_000) + 1) * 60_000
}

function describe(e: unknown): ConfigError[] {
  if (e instanceof ConfigRejected) return e.errors
  return [{ field: '<request>', message: e instanceof Error ? e.message : String(e) }]
}

export function ConfigControl({ parameters, effectiveFrom, onSaved, api = API }: Props) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'parameters' | 'factors' | 'versions'>('parameters')
  const [fields, setFields] = useState<ParameterField[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [appliedAt, setAppliedAt] = useState<number | null>(null)
  const now = useNow(5_000)

  useEffect(() => {
    if (!open || fields) return
    let live = true
    api.schema().then(
      (f) => {
        if (live) setFields(f)
      },
      (e: unknown) => {
        if (live) setLoadError(e instanceof Error ? e.message : String(e))
      },
    )
    return () => {
      live = false
    }
  }, [open, fields, api])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.querySelector('[role="tooltip"]')) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const saved = (p: ParametersOut) => {
    const at = nextMinute()
    setAppliedAt(at)
    onSaved(p, at)
  }
  const pending = appliedAt ?? effectiveFrom
  const factorsOff = FACTOR_SCOPES.reduce(
    (n, s) => n + offNames(factorSwitches(parameters?.params, s.scope)).length,
    0,
  )

  return (
    <div className="relative flex items-center gap-2 text-xs">
      <button
        type="button"
        className={`${toolClass(open)} ${open ? 'relative z-50 bg-bg-elev' : ''}`}
        aria-expanded={open}
        title={parameters ? `Config version ${String(parameters.version)}: ${parameters.tag}` : ''}
        onClick={() => {
          setOpen((o) => !o)
        }}
      >
        <ConfigIcon />
        Config {/* the tag is in the title and the drawer: a long one would push the bar wide */}
        <span className="font-mono text-fg">
          {parameters ? `v${String(parameters.version)}` : '—'}
        </span>
      </button>
      {pending && pending > now ? (
        <span className="text-fg-muted" role="status">
          applies from {fmtIstTime(pending)}
        </span>
      ) : null}
      {open && parameters ? (
        <>
          <div
            className="fixed inset-0 z-30 bg-black/30"
            aria-hidden="true"
            data-testid="config-backdrop"
            onClick={() => {
              setOpen(false)
            }}
          />
          <aside
            role="dialog"
            aria-label="Config"
            className="fixed inset-y-0 right-0 z-40 flex w-[min(600px,100vw)] flex-col whitespace-normal border-l border-border bg-bg-elev text-[13px] shadow-xl"
            data-testid="config-panel"
          >
            <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-4 py-3">
              <button
                type="button"
                title="Close config"
                className="flex min-w-0 flex-1 items-baseline gap-2 text-left"
                onClick={() => {
                  setOpen(false)
                }}
              >
                <h2 className="text-sm font-semibold text-fg">Config</h2>
                <span className="truncate text-xs text-fg-muted">
                  in force: <span className="font-mono text-fg">v{parameters.version}</span>{' '}
                  {parameters.tag}, saved {fmtDate(parameters.created_ts)}{' '}
                  {fmtIstTime(parameters.created_ts)}
                </span>
              </button>
              <button
                type="button"
                aria-label="Close config"
                className="flex shrink-0 items-center gap-1 rounded border border-border bg-bg-row px-2.5 py-1 text-xs font-medium text-fg hover:border-accent hover:text-accent"
                onClick={() => {
                  setOpen(false)
                }}
              >
                <span aria-hidden="true" className="text-base leading-none">
                  ✕
                </span>
                Close
              </button>
            </div>
            <div className="flex shrink-0 gap-1 border-b border-border/60 px-4 py-2" role="tablist">
              {(['parameters', 'factors', 'versions'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={tab === t}
                  className={`rounded px-3 py-1 ${
                    tab === t ? 'bg-bg-row text-fg' : 'text-fg-muted hover:text-fg'
                  }`}
                  onClick={() => {
                    setTab(t)
                  }}
                >
                  {t === 'versions'
                    ? 'Versions'
                    : t === 'parameters'
                      ? 'Parameters'
                      : `Factors${factorsOff > 0 ? ` · ${String(factorsOff)} off` : ''}`}
                </button>
              ))}
            </div>
            {tab === 'parameters' ? (
              fields ? (
                <Editor parameters={parameters} fields={fields} save={api.save} onSaved={saved} />
              ) : (
                <div className="p-4 text-fg-muted" role={loadError ? 'alert' : undefined}>
                  {loadError ? `Could not load the parameters: ${loadError}` : 'Loading…'}
                </div>
              )
            ) : tab === 'factors' ? (
              <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
                <FactorsTab parameters={parameters} setFactor={api.setFactor} onSaved={saved} />
              </div>
            ) : (
              <History key={parameters.version} api={api} onSaved={saved} />
            )}
          </aside>
        </>
      ) : null}
    </div>
  )
}

interface EditorProps {
  parameters: ParametersOut
  fields: ParameterField[]
  save: ConfigApi['save']
  onSaved: (p: ParametersOut) => void
}

/** Values the user has not touched follow `next`; edited ones are kept. */
function rebase(prev: Draft, next: Draft, draft: Draft): Draft {
  const out: Draft = { ...next }
  for (const [k, v] of Object.entries(draft)) if (v !== prev[k]) out[k] = v
  return out
}

function Editor({ parameters, fields, save, onSaved }: EditorProps) {
  const base = useMemo(() => flatten(parameters.params), [parameters])
  const [draft, setDraft] = useState<Draft>(base)
  const prevBase = useRef(base)
  useEffect(() => {
    // a factor flip or a save made a new version: keep unsaved edits, take the rest
    if (prevBase.current === base) return
    const prev = prevBase.current
    prevBase.current = base
    setDraft((d) => rebase(prev, base, d))
  }, [base])
  const [tag, setTag] = useState('')
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<ConfigError[]>([])

  const changed = useMemo(() => new Set(changedPaths(base, draft)), [base, draft])
  const groups = useMemo(() => {
    const out = new Map<string, ParameterField[]>()
    for (const f of fields) out.set(f.group, [...(out.get(f.group) ?? []), f])
    return [...out.entries()]
  }, [fields])

  const known = new Set<string>([...fields.map((f) => f.path), ...groups.map(([g]) => g), 'tag'])
  const errorAt = (where: string) => errors.filter((e) => e.field === where)
  const general = errors.filter((e) => !known.has(e.field))

  const submit = async () => {
    setBusy(true)
    setErrors([])
    try {
      const p = await save(tag.trim(), toValues(parameters.params, fields, draft))
      setTag('')
      onSaved(p)
    } catch (e: unknown) {
      setErrors(describe(e))
    } finally {
      setBusy(false)
    }
  }

  const set = (path: string, value: string) => {
    setDraft((d) => ({ ...d, [path]: value }))
  }

  return (
    <form
      className="flex min-h-0 flex-col"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        {general.map((e) => (
          <div key={`${e.field}:${e.message}`} className="mb-2 text-bear" role="alert">
            {e.message}
          </div>
        ))}
        {groups.map(([group, members]) => (
          <fieldset key={group} className="mb-4">
            <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg">
              {group}
            </legend>
            {errorAt(group).map((e) => (
              <div key={e.message} className="text-bear" role="alert">
                {e.message}
              </div>
            ))}
            {members.map((f) => {
              const limits = limitsText(f)
              const bad = errorAt(f.path)
              const border = bad.length
                ? 'border-bear'
                : changed.has(f.path)
                  ? 'border-accent'
                  : 'border-border'
              const common = {
                id: `cfg-${f.path}`,
                'aria-label': f.path,
                'aria-invalid': bad.length > 0,
                className: `${INPUT} ${border}`,
                value: draft[f.path] ?? '',
              }
              return (
                <div key={f.path} className="flex items-start gap-3 border-t border-border/40 py-2">
                  <div className="min-w-0 flex-1">
                    <label htmlFor={`cfg-${f.path}`} className="font-mono">
                      {f.key}
                    </label>
                    {changed.has(f.path) ? (
                      <span className="ml-2 text-xs text-accent">was {base[f.path]}</span>
                    ) : null}
                    <p className="mt-0.5 text-xs leading-relaxed text-fg-muted">{f.help}</p>
                    {limits ? (
                      <p className="text-[11px] leading-relaxed text-fg-muted/80">
                        Allowed: {limits}
                      </p>
                    ) : null}
                    {bad.map((e) => (
                      <span key={e.message} className="block text-bear" role="alert">
                        {e.message}
                      </span>
                    ))}
                  </div>
                  {f.kind === 'choice' ? (
                    <select
                      {...common}
                      className={`${BOX} ${border} w-36 shrink-0 font-mono`}
                      onChange={(e) => {
                        set(f.path, e.target.value)
                      }}
                    >
                      {(f.choices ?? []).map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      {...common}
                      type={f.kind === 'time' ? 'time' : 'text'}
                      inputMode={f.kind === 'time' ? undefined : 'decimal'}
                      onChange={(e) => {
                        set(f.path, e.target.value)
                      }}
                    />
                  )}
                </div>
              )
            })}
          </fieldset>
        ))}
      </div>
      <div className="shrink-0 border-t border-border/60 px-4 py-3">
        {errorAt('tag').map((e) => (
          <div key={e.message} className="mb-1 text-bear" role="alert">
            Tag: {e.message}
          </div>
        ))}
        <div className="flex items-center gap-2">
          <input
            aria-label="Tag for this version"
            placeholder="Tag for this version, e.g. higher entry bar"
            className={TEXT}
            maxLength={MAX_TAG}
            value={tag}
            onChange={(e) => {
              setTag(e.target.value)
            }}
          />
          <button
            type="button"
            className={BUTTON}
            disabled={busy || changed.size === 0}
            onClick={() => {
              setDraft(base)
              setErrors([])
            }}
          >
            Discard
          </button>
          <button
            type="submit"
            className={`${BUTTON} border-accent text-accent hover:text-accent`}
            disabled={busy || changed.size === 0 || tag.trim() === ''}
          >
            {busy ? 'Saving…' : `Save as v${String(parameters.version + 1)}`}
          </button>
        </div>
        <div className="mt-1 text-[11px] text-fg-muted">
          {changed.size === 0
            ? 'Nothing changed yet.'
            : `${String(changed.size)} value${changed.size === 1 ? '' : 's'} changed. A save applies from the next minute close.`}
        </div>
      </div>
    </form>
  )
}

/** Factor switches per index and metal (E16). Each flip is saved at once as its own version,
 * tagged `Factor NIFTY.pcr: off`, and applies from the next minute close. */
function FactorsTab({
  parameters,
  setFactor: flip,
  onSaved,
}: {
  parameters: ParametersOut
  setFactor: ConfigApi['setFactor']
  onSaved: (p: ParametersOut) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [errors, setErrors] = useState<ConfigError[]>([])

  const change = async (scope: string, name: string, enabled: boolean) => {
    setBusy(`${scope}.${name}`)
    setErrors([])
    try {
      const p = await flip(scope, name, enabled)
      if (p.version !== parameters.version) onSaved(p)
    } catch (e: unknown) {
      setErrors(describe(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="mb-4" data-testid="factors-tab">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg">Factors</h3>
      <p className="mb-2 text-xs leading-relaxed text-fg-muted">
        A factor switched off is shown in the Evidence panel but carries no weight in that
        index&apos;s or metal&apos;s bias. Each switch is saved at once as a new version and applies
        from the next minute close.
      </p>
      {errors.map((e) => (
        <div key={e.message} className="mb-2 text-bear" role="alert">
          {e.message}
        </div>
      ))}
      {FACTOR_SCOPES.map(({ scope, label }) => {
        const switches = factorSwitches(parameters.params, scope)
        if (!switches) return null
        const off = offNames(switches).length
        return (
          <fieldset key={scope} className="mb-3">
            <legend className="text-[10px] uppercase tracking-wide text-fg-muted">
              {label}
              {off > 0 ? <span className="ml-2 normal-case text-warn">{off} off</span> : null}
            </legend>
            {Object.entries(switches).map(([name, value]) => {
              const on = value !== 'off'
              const factor = FACTOR_LABEL[name] ?? name
              const help = FACTOR_HELP[name]
              return (
                <div
                  key={name}
                  className={`flex items-start gap-3 border-t border-border/40 py-2 ${on ? '' : 'opacity-60'}`}
                >
                  <FactorSwitch
                    on={on}
                    label={`${label}: ${factor}`}
                    busy={busy !== null}
                    title={on ? `Leave ${factor} out of ${label}` : `Count ${factor} in ${label}`}
                    onChange={(enabled) => {
                      void change(scope, name, enabled)
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-fg">{factor}</div>
                    {help ? <p className="text-xs leading-relaxed text-fg-muted">{help}</p> : null}
                  </div>
                  {busy === `${scope}.${name}` ? (
                    <span className="shrink-0 text-xs text-fg-muted">saving…</span>
                  ) : null}
                </div>
              )
            })}
          </fieldset>
        )
      })}
    </section>
  )
}

const SOURCE: Record<ConfigVersionOut['source'], string> = {
  seed: 'from params.toml',
  edit: 'edited',
  revert: 'revert',
}

function History({ api, onSaved }: { api: ConfigApi; onSaved: (p: ParametersOut) => void }) {
  const [rows, setRows] = useState<ConfigVersionOut[] | null>(null)
  const [errors, setErrors] = useState<ConfigError[]>([])
  const [target, setTarget] = useState<{ version: number; tag: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    api.versions().then(
      (v) => {
        if (live) setRows(v)
      },
      (e: unknown) => {
        if (live) setErrors(describe(e))
      },
    )
    return () => {
      live = false
    }
  }, [api])

  const revert = async () => {
    if (!target) return
    setBusy(true)
    setErrors([])
    try {
      onSaved(await api.revert(target.version, target.tag.trim() || undefined))
    } catch (e: unknown) {
      setErrors(describe(e))
      setBusy(false)
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto px-4 py-3" data-testid="config-history">
      {errors.map((e) => (
        <div key={`${e.field}:${e.message}`} className="mb-2 text-bear" role="alert">
          {e.message}
        </div>
      ))}
      {rows === null && errors.length === 0 ? <div className="text-fg-muted">Loading…</div> : null}
      {(rows ?? []).map((v) => (
        <div
          key={v.version}
          className="border-t border-border/40 py-1.5"
          data-testid={`config-version-${String(v.version)}`}
        >
          <div className="flex items-baseline gap-2">
            <span className="w-8 shrink-0 font-mono text-fg">v{v.version}</span>
            <span className="min-w-0 flex-1 truncate" title={v.tag}>
              {v.tag}
            </span>
            {v.active ? (
              <span className="shrink-0 rounded border border-bull px-1.5 text-xs text-bull">
                in force
              </span>
            ) : (
              <button
                type="button"
                className={BUTTON}
                disabled={busy}
                aria-label={`Revert to version ${String(v.version)}`}
                onClick={() => {
                  setTarget({ version: v.version, tag: `Revert to v${String(v.version)}` })
                }}
              >
                Revert
              </button>
            )}
          </div>
          <div className="pl-10 text-[11px] text-fg-muted">
            {fmtDate(v.created_ts)} {fmtIstTime(v.created_ts)} · {SOURCE[v.source]}
            {v.reverted_from != null ? ` to v${String(v.reverted_from)}` : ''}
          </div>
          {target?.version === v.version ? (
            <div className="mt-1 flex items-center gap-2 pl-10">
              <input
                aria-label="Tag for the reverted version"
                className={TEXT}
                maxLength={MAX_TAG}
                value={target.tag}
                onChange={(e) => {
                  setTarget({ version: v.version, tag: e.target.value })
                }}
              />
              <button
                type="button"
                className={BUTTON}
                disabled={busy}
                onClick={() => {
                  setTarget(null)
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`${BUTTON} border-accent text-accent hover:text-accent`}
                disabled={busy}
                onClick={() => {
                  void revert()
                }}
              >
                {busy ? 'Reverting…' : 'Confirm revert'}
              </button>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  )
}
