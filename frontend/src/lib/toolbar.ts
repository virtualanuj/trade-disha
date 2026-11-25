/**
 * A tool in the top bar (Data, Config, Latency, Headlines…): borderless, icon and label,
 * so tools read differently from the page tabs and the status strip.
 */
export function toolClass(active = false): string {
  return (
    'inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-1 hover:bg-bg-row ' +
    'hover:text-fg disabled:opacity-50 ' +
    (active ? 'bg-accent/10 text-accent' : 'text-fg-muted')
  )
}
