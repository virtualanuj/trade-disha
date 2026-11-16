import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { getConfigVersion } from '../../api/client'
import type { ConfigVersionDetail } from '../../api/types'
import { changedPaths, flatten } from '../../lib/config'
import { fmtDate, fmtIstTime } from '../../lib/format'
import { useMarketStore } from '../../state/store'

interface Props {
  /** the config version a signal fired under; nothing is drawn for null */
  version: number | null
  load?: (version: number) => Promise<ConfigVersionDetail>
}

const WIDTH = 420
const CLOSE_DELAY_MS = 150

type Loaded = { kind: 'loading' } | { kind: 'ok'; detail: ConfigVersionDetail } | { kind: 'error' }

/**
 * "v7": the config version a signal fired under. Hovering or focusing it shows that
 * version's tag and values, marking the ones that differ from the config now in force.
 */
export function ConfigVersionChip({ version, load = getConfigVersion }: Props) {
  const current = useMarketStore((s) => s.parameters)
  const anchor = useRef<HTMLButtonElement>(null)
  const closing = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [at, setAt] = useState<{
    left: number
    top?: number
    bottom?: number
    maxHeight: number
  } | null>(null)
  const [loaded, setLoaded] = useState<Loaded>({ kind: 'loading' })

  useEffect(
    () => () => {
      if (closing.current) clearTimeout(closing.current)
    },
    [],
  )

  if (version === null) return null

  const show = () => {
    if (closing.current) clearTimeout(closing.current)
    const r = anchor.current?.getBoundingClientRect()
    if (!r) return
    // fixed to the window, so the scrolling column cannot clip it; below if there is room
    const below = window.innerHeight - r.bottom
    const above = r.top
    const under = below >= 240 || below >= above
    setAt({
      left: Math.max(8, Math.min(r.left, window.innerWidth - WIDTH - 8)),
      // above, it grows upward from the chip, so the pointer can reach it
      ...(under ? { top: r.bottom + 4 } : { bottom: window.innerHeight - r.top + 4 }),
      maxHeight: Math.max(120, (under ? below : above) - 12),
    })
    if (loaded.kind !== 'ok') {
      load(version).then(
        (detail) => {
          setLoaded({ kind: 'ok', detail })
        },
        () => {
          setLoaded({ kind: 'error' })
        },
      )
    }
  }
  const hide = () => {
    if (closing.current) clearTimeout(closing.current)
    closing.current = setTimeout(() => {
      setAt(null)
    }, CLOSE_DELAY_MS)
  }

  return (
    <>
      <button
        ref={anchor}
        type="button"
        className="rounded border border-border px-1 font-mono text-[10px] leading-4 text-fg-muted hover:text-fg"
        aria-label={`Config version ${String(version)}`}
        aria-expanded={at !== null}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        v{version}
      </button>
      {/* drawn on the page body: a dimmed shadow row must not dim or clip it */}
      {at
        ? createPortal(
            <div
              role="tooltip"
              className="fixed z-30 overflow-auto rounded border border-border bg-bg-elev p-3 text-left font-sans text-xs text-fg shadow-lg"
              style={{
                left: at.left,
                top: at.top,
                bottom: at.bottom,
                width: WIDTH,
                maxHeight: at.maxHeight,
              }}
              data-testid={`config-version-tip-${String(version)}`}
              onMouseEnter={show}
              onMouseLeave={hide}
            >
              {loaded.kind === 'loading' ? <span className="text-fg-muted">Loading…</span> : null}
              {loaded.kind === 'error' ? (
                <span className="text-bear">Could not load config v{version}.</span>
              ) : null}
              {loaded.kind === 'ok' ? (
                <Values detail={loaded.detail} current={current ? flatten(current.params) : null} />
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </>
  )
}

function Values({
  detail,
  current,
}: {
  detail: ConfigVersionDetail
  current: Record<string, string> | null
}) {
  const values = flatten(detail.params)
  const differs = new Set(current ? changedPaths(values, current) : [])
  const groups = new Map<string, [string, string][]>()
  for (const [path, value] of Object.entries(values)) {
    const dot = path.indexOf('.')
    const group = path.slice(0, dot)
    groups.set(group, [...(groups.get(group) ?? []), [path, value]])
  }
  return (
    <>
      <div className="flex items-baseline gap-2">
        <span className="font-mono font-semibold">v{detail.version}</span>
        <span className="min-w-0 flex-1 truncate">{detail.tag}</span>
      </div>
      <div className="text-[11px] text-fg-muted">
        saved {fmtDate(detail.created_ts)} {fmtIstTime(detail.created_ts)}
        {current
          ? detail.active || differs.size === 0
            ? ' · same values as the config in force'
            : ` · ${String(differs.size)} value${differs.size === 1 ? ' differs' : 's differ'} from the config in force`
          : ''}
      </div>
      <div className="mt-2 columns-2 gap-4">
        {[...groups.entries()].map(([group, rows]) => (
          <div key={group} className="mb-2 break-inside-avoid">
            <div className="text-[10px] uppercase tracking-wide text-fg-muted">{group}</div>
            {rows.map(([path, value]) => (
              <div
                key={path}
                className={`flex justify-between gap-2 font-mono text-[11px] ${
                  differs.has(path) ? 'text-accent' : ''
                }`}
                data-differs={differs.has(path) ? 'true' : undefined}
                title={
                  differs.has(path) && current ? `now ${current[path] ?? 'not set'}` : undefined
                }
              >
                <span className="min-w-0 truncate text-fg-muted">
                  {path.slice(group.length + 1)}
                </span>
                <span>{value}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  )
}
