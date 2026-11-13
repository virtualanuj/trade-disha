import type { ReactNode } from 'react'

interface Props {
  /** what the panel holds, for the button labels: "option chain" */
  name: string
  open: boolean
  onToggle: () => void
  /** pixels, when open */
  width: number
  className?: string
  children: ReactNode
}

/**
 * A right-hand panel that can be hidden. Hidden, it leaves a narrow strip with a button to
 * bring it back; its contents are not rendered, but the data behind them keeps updating.
 */
export function SidePanel({ name, open, onToggle, width, className = '', children }: Props) {
  if (!open) {
    return (
      <aside className="flex w-7 shrink-0 flex-col items-center border-l border-border bg-bg-elev">
        <button
          type="button"
          className="flex h-full w-full flex-col items-center gap-2 pt-3 text-xs text-fg-muted hover:text-fg"
          aria-expanded={false}
          aria-label={`Show ${name}`}
          title={`Show ${name}`}
          onClick={onToggle}
        >
          <span aria-hidden="true">‹</span>
          <span aria-hidden="true" className="[writing-mode:vertical-rl]">
            {name}
          </span>
        </button>
      </aside>
    )
  }
  return (
    <aside
      className={`relative flex shrink-0 flex-col bg-bg-elev p-4 ${className}`}
      style={{ width }}
    >
      <button
        type="button"
        className="absolute top-1 right-1 z-10 rounded px-1.5 text-sm leading-5 text-fg-muted hover:bg-bg-row hover:text-fg"
        aria-expanded
        aria-label={`Hide ${name}`}
        title={`Hide ${name}`}
        onClick={onToggle}
      >
        <span aria-hidden="true">›</span>
      </button>
      {children}
    </aside>
  )
}
