import { Fragment } from 'react'

import type { TabGroup } from '../../lib/tabs'

interface Props {
  groups: TabGroup[]
  selected: string
  onSelect: (id: string) => void
}

/** The dashboard's tabs grouped by exchange (E32): NSE (indices, BULLION ETFs), MCX (metals). */
export function IndexTabs({ groups, selected, onSelect }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Market"
      className="flex flex-wrap items-end gap-1 border-b border-border"
    >
      {groups.map((g, gi) => (
        <Fragment key={g.exchange}>
          {gi > 0 ? (
            <span aria-hidden="true" className="mx-2 mb-2 h-4 w-px self-end bg-border" />
          ) : null}
          <span className="mr-1 mb-2 text-[10px] font-semibold tracking-wide text-fg-muted">
            {g.exchange}
          </span>
          {g.tabs.map((t) => {
            const active = t.id === selected
            return (
              <button
                key={t.id}
                role="tab"
                type="button"
                aria-selected={active}
                aria-label={`${g.exchange} ${t.label}`}
                onClick={() => {
                  onSelect(t.id)
                }}
                className={`-mb-px border-b-2 px-3 py-1.5 text-sm font-medium ${
                  active
                    ? 'border-accent text-fg'
                    : 'border-transparent text-fg-muted hover:text-fg'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </Fragment>
      ))}
    </div>
  )
}
