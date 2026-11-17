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
  /** shows a hide (×) button that takes the panel off the page (the headlines, E10) */
  onClose?: (() => void) | undefined
  /**
   * shows the move up / down buttons; a direction with nowhere to go is null and its
   * button is disabled
   */
  move?: { up: (() => void) | null; down: (() => void) | null } | undefined
  /** what the move buttons say they move, when the panel moves with another */
  moveLabel?: string | undefined
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

const ICON = {
  viewBox: '0 0 12 12',
  width: 12,
  height: 12,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
} as const

const BUTTON =
  'flex h-6 w-6 shrink-0 items-center justify-center rounded text-fg-muted hover:bg-bg-row hover:text-fg disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-fg-muted'

/**
 * The frame every dashboard panel sits in: a title bar with a minimise button around the
 * panel's contents, and move up / down buttons for a panel that can be reordered. Minimised, only the title bar is left, with a one-line summary, and
 * the panels below move up.
 */
export function PanelFrame({
  id,
  title,
  summary,
  minimised,
  onToggle,
  onClose,
  move,
  moveLabel,
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
        <span className="ml-auto flex shrink-0 items-center">
          {move
            ? (['up', 'down'] as const).map((dir) => (
                <button
                  key={dir}
                  type="button"
                  className={BUTTON}
                  aria-label={`Move ${moveLabel ?? name} ${dir}`}
                  title={`Move ${moveLabel ?? name} ${dir}`}
                  disabled={move[dir] === null}
                  onClick={move[dir] ?? undefined}
                >
                  <svg {...ICON}>
                    <path d={dir === 'up' ? 'M6 9.5v-7M3 5.5l3-3 3 3' : 'M6 2.5v7M3 6.5l3 3 3-3'} />
                  </svg>
                </button>
              ))
            : null}
          <button
            type="button"
            className={BUTTON}
            aria-expanded={!minimised}
            aria-label={`${action} ${name}`}
            title={`${action} ${name}`}
            onClick={onToggle}
          >
            <svg {...ICON}>
              <path d={minimised ? 'M2.5 4.5 6 8l3.5-3.5' : 'M2.5 9.5h7'} />
            </svg>
          </button>
          {onClose ? (
            <button
              type="button"
              className={BUTTON}
              aria-label={`Hide ${name}`}
              title={`Hide ${name}`}
              onClick={onClose}
            >
              <svg {...ICON}>
                <path d="M3 3l6 6M9 3l-6 6" />
              </svg>
            </button>
          ) : null}
        </span>
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
