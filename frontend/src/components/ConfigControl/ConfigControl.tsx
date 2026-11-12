import { useState } from 'react'

import { ReloadFailed, reloadParameters, type ReloadError } from '../../api/client'
import type { ParametersOut } from '../../api/types'
import { fmtIstTime } from '../../lib/format'
import { useNow } from '../../lib/useNow'

interface Props {
  parameters: ParametersOut | null
  effectiveFrom: number | null
  onReloaded: (p: ParametersOut, effectiveFrom: number) => void
}

function formatValue(v: unknown): string {
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  return JSON.stringify(v)
}

type Status =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'ok'; at: number }
  | { kind: 'invalid'; errors: ReloadError[] }
  | { kind: 'error'; message: string }

export function ConfigControl({ parameters, effectiveFrom, onReloaded }: Props) {
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [open, setOpen] = useState(false)
  const now = useNow(5_000)

  const reload = async () => {
    setStatus({ kind: 'busy' })
    try {
      const p = await reloadParameters()
      const next = (Math.floor(Date.now() / 60_000) + 1) * 60_000
      onReloaded(p, next)
      setStatus({ kind: 'ok', at: next })
    } catch (e: unknown) {
      if (e instanceof ReloadFailed) setStatus({ kind: 'invalid', errors: e.errors })
      else setStatus({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
    }
  }

  return (
    <div className="relative flex items-center gap-2 text-xs">
      <button
        type="button"
        className="text-fg-muted hover:text-fg"
        onClick={() => {
          setOpen((o) => !o)
        }}
        title={parameters?.path}
      >
        Config{' '}
        <span className="font-mono">{parameters ? fmtIstTime(parameters.loaded_at) : '—'}</span>
      </button>
      <button
        type="button"
        onClick={() => {
          void reload()
        }}
        disabled={status.kind === 'busy'}
        className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg disabled:opacity-50"
      >
        {status.kind === 'busy' ? 'Reloading…' : 'Reload config'}
      </button>
      {status.kind === 'ok' ? (
        <span className="text-bull" role="status">
          applies from {fmtIstTime(status.at)}
        </span>
      ) : null}
      {status.kind === 'invalid' ? (
        <span
          className="text-bear"
          role="alert"
          title={status.errors.map((e) => `${e.field}: ${e.message}`).join('\n')}
        >
          invalid: {status.errors[0]?.field} — {status.errors[0]?.message}
          {status.errors.length > 1 ? ` (+${String(status.errors.length - 1)} more)` : ''}; previous
          values kept
        </span>
      ) : null}
      {status.kind === 'error' ? (
        <span className="text-bear" role="alert">
          {status.message}
        </span>
      ) : null}
      {status.kind === 'idle' && effectiveFrom && effectiveFrom > now ? (
        <span className="text-fg-muted">new config from {fmtIstTime(effectiveFrom)}</span>
      ) : null}
      {open && parameters ? (
        <div className="absolute top-7 right-0 z-20 max-h-[70vh] w-[420px] overflow-auto rounded border border-border bg-bg-elev p-3 shadow-lg">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="font-semibold">Active parameters</span>
            <span className="font-mono text-fg-muted">{parameters.path}</span>
          </div>
          {Object.entries(parameters.params).map(([group, values]) => (
            <div key={group} className="mb-2">
              <div className="text-[10px] uppercase tracking-wide text-fg-muted">{group}</div>
              <table className="w-full font-mono">
                <tbody>
                  {Object.entries(values).map(([k, v]) => (
                    <tr key={k} className="h-5">
                      <td className="pr-3 text-fg-muted">{k}</td>
                      <td className="text-right">{formatValue(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
