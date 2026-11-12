interface Props {
  indices: string[]
  selected: string
  onSelect: (index: string) => void
}

export function IndexTabs({ indices, selected, onSelect }: Props) {
  return (
    <div role="tablist" aria-label="Index" className="flex gap-1 border-b border-border">
      {indices.map((i) => {
        const active = i === selected
        return (
          <button
            key={i}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => {
              onSelect(i)
            }}
            className={`-mb-px border-b-2 px-3 py-1.5 text-sm font-medium ${
              active ? 'border-accent text-fg' : 'border-transparent text-fg-muted hover:text-fg'
            }`}
          >
            {i}
          </button>
        )
      })}
    </div>
  )
}
