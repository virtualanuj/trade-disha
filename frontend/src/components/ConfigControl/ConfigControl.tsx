import { useEffect, useMemo, useState } from 'react'

import {
  ConfigRejected,
  fetchParameterSchema,
  listConfigVersions,
  revertConfigVersion,
  saveParameters,
  type ConfigError,
} from '../../api/client'
import type { ConfigVersionOut, ParameterField, ParametersOut, ParamValues } from '../../api/types'
import { changedPaths, flatten, limitsText, toValues, type Draft } from '../../lib/config'
import { fmtDate, fmtIstTime } from '../../lib/format'
import { useNow } from '../../lib/useNow'

export interface ConfigApi {
  schema: () => Promise<ParameterField[]>
  save: (tag: string, params: ParamValues) => Promise<ParametersOut>
  versions: () => Promise<ConfigVersionOut[]>
  revert: (version: number, tag?: string) => Promise<ParametersOut>
}

const API: ConfigApi = {
  schema: fetchParameterSchema,
  save: saveParameters,
  versions: listConfigVersions,
  revert: revertConfigVersion,
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
  const [tab, setTab] = useState<'edit' | 'history'>('edit')
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

  const saved = (p: ParametersOut) => {
    const at = nextMinute()
    setAppliedAt(at)
    onSaved(p, at)
  }
  const pending = appliedAt ?? effectiveFrom

  return (
    <div className="relative flex items-center gap-2 text-xs">
      <button
        type="button"
        className={BUTTON}
        aria-expanded={open}
        title={parameters ? `Config version ${String(parameters.version)}: ${parameters.tag}` : ''}
        onClick={() => {
          setOpen((o) => !o)
        }}
      >
        Config{' '}
        {parameters ? (
          <>
            <span className="font-mono text-fg">v{parameters.version}</span>
            <span className="ml-1 inline-block max-w-40 truncate align-bottom">
              {parameters.tag}
            </span>
          </>
        ) : (
          '—'
        )}
      </button>
      {pending && pending > now ? (
        <span className="text-fg-muted" role="status">
          applies from {fmtIstTime(pending)}
        </span>
      ) : null}
      {open && parameters ? (
        <div
          className="absolute top-7 right-0 z-20 flex max-h-[78vh] w-[540px] flex-col whitespace-normal rounded border border-border bg-bg-elev shadow-lg"
          data-testid="config-panel"
        >
          <div className="flex shrink-0 items-center gap-1 border-b border-border/60 px-3 py-2">
            {(['edit', 'history'] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                className={`rounded px-2 py-0.5 ${
                  tab === t ? 'bg-bg-row text-fg' : 'text-fg-muted hover:text-fg'
                }`}
                onClick={() => {
                  setTab(t)
                }}
              >
                {t === 'edit' ? 'Edit' : 'History'}
              </button>
            ))}
            <span className="ml-auto text-fg-muted">
              in force: <span className="font-mono text-fg">v{parameters.version}</span>, saved{' '}
              {fmtDate(parameters.created_ts)} {fmtIstTime(parameters.created_ts)}
            </span>
          </div>
          {tab === 'edit' ? (
            fields ? (
              <Editor
                key={parameters.version}
                parameters={parameters}
                fields={fields}
                save={api.save}
                onSaved={saved}
              />
            ) : (
              <div className="p-3 text-fg-muted" role={loadError ? 'alert' : undefined}>
                {loadError ? `Could not load the fields: ${loadError}` : 'Loading…'}
              </div>
            )
          ) : (
            <History key={parameters.version} api={api} onSaved={saved} />
          )}
        </div>
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

function Editor({ parameters, fields, save, onSaved }: EditorProps) {
  const base = useMemo(() => flatten(parameters.params), [parameters])
  const [draft, setDraft] = useState<Draft>(base)
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
      onSaved(await save(tag.trim(), toValues(parameters.params, fields, draft)))
    } catch (e: unknown) {
      setErrors(describe(e))
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
      <div className="min-h-0 flex-1 overflow-auto px-3 py-2">
        {general.map((e) => (
          <div key={`${e.field}:${e.message}`} className="mb-2 text-bear" role="alert">
            {e.message}
          </div>
        ))}
        {groups.map(([group, members]) => (
          <fieldset key={group} className="mb-3">
            <legend className="text-[10px] uppercase tracking-wide text-fg-muted">{group}</legend>
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
                <div key={f.path} className="flex items-start gap-3 border-t border-border/40 py-1">
                  <label htmlFor={`cfg-${f.path}`} className="min-w-0 flex-1">
                    <span className="font-mono">{f.key}</span>
                    {changed.has(f.path) ? (
                      <span className="ml-2 text-accent">was {base[f.path]}</span>
                    ) : null}
                    <span className="block text-[11px] leading-snug text-fg-muted">
                      {f.help}
                      {limits ? ` (${limits})` : ''}
                    </span>
                    {bad.map((e) => (
                      <span key={e.message} className="block text-bear" role="alert">
                        {e.message}
                      </span>
                    ))}
                  </label>
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
      <div className="shrink-0 border-t border-border/60 px-3 py-2">
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
    <div className="min-h-0 flex-1 overflow-auto px-3 py-2" data-testid="config-history">
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
              <span className="shrink-0 text-bull">in force</span>
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
