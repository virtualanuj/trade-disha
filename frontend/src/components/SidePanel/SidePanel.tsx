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
 * The right-hand column. Hidden (its panel minimised), it leaves a narrow strip with a
 * button to bring it back; its contents are not rendered, but the data behind them keeps
 * updating. Shown, the panel frame inside carries the button that hides it.
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
    <aside className={`flex shrink-0 flex-col p-4 pl-2 ${className}`} style={{ width }}>
      {children}
    </aside>
  )
}
