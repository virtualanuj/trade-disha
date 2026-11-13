import type { ReactNode } from 'react'

import type { PanelId } from '../../lib/panels'

interface Props {
  id: PanelId
  /** shown on the title bar: "Price chart" */
  title: string
  /** one line shown on the title bar while the panel is minimised */
  summary?: ReactNode
  minimised: boolean
  /** minimise, or expand again when already minimised */
  onToggle: () => void
  /** keep the contents in the page (hidden) while minimised, so they keep their own state */
  keepMounted?: boolean
  /** take the full height of the parent, with the contents filling what the bar leaves */
  fill?: boolean
  /** border colour of the box; the panel's accent when it has one */
  border?: string
  /** classes for the contents area; padding by default */
  bodyClassName?: string
  children: ReactNode
}

/**
 * The frame every dashboard panel sits in: a title bar with a minimise button around the
 * panel's contents. Minimised, only the title bar is left, with a one-line summary, and
 * the panels below move up.
 */
export function PanelFrame({
  id,
  title,
  summary,
  minimised,
  onToggle,
  keepMounted = false,
  fill = false,
  border = 'border-border',
  bodyClassName = 'p-3',
  children,
}: Props) {
  const name = title.toLowerCase()
  const action = minimised ? 'Expand' : 'Minimise'
  return (
    <div
      className={`rounded border bg-bg-elev ${border} ${
        fill && !minimised ? 'flex h-full min-h-0 flex-col' : ''
      }`}
      data-panel={id}
      data-state={minimised ? 'minimised' : 'normal'}
      data-testid={`panel-${id}`}
    >
      <div
        className={`flex h-8 shrink-0 items-center gap-3 pr-1 pl-3 ${
          minimised ? '' : 'border-b border-border/60'
        }`}
      >
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-fg-muted">{title}</span>
        {minimised && summary != null ? (
          <span className="min-w-0 truncate font-mono text-xs">{summary}</span>
        ) : null}
        <button
          type="button"
          className="ml-auto flex h-6 w-6 shrink-0 items-center justify-center rounded text-fg-muted hover:bg-bg-row hover:text-fg"
          aria-expanded={!minimised}
          aria-label={`${action} ${name}`}
          title={`${action} ${name}`}
          onClick={onToggle}
        >
          <svg
            viewBox="0 0 12 12"
            width="12"
            height="12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d={minimised ? 'M2.5 4.5 6 8l3.5-3.5' : 'M2.5 9.5h7'} />
          </svg>
        </button>
      </div>
      {minimised ? (
        keepMounted ? (
          <div hidden>{children}</div>
        ) : null
      ) : (
        <div className={fill ? `min-h-0 flex-1 overflow-auto ${bodyClassName}` : bodyClassName}>
          {children}
        </div>
      )}
    </div>
  )
}
