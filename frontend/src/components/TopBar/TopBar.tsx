import type { Theme } from '../../theme/useTheme'

export type BackendState =
  | { kind: 'checking' }
  | { kind: 'up'; version: string; milestone: number }
  | { kind: 'down'; error: string }

interface Props {
  backend: BackendState
  theme: Theme
  onToggleTheme: () => void
}

function BackendPill({ backend }: { backend: BackendState }) {
  if (backend.kind === 'checking') {
    return <span className="text-fg-muted">Backend: checking…</span>
  }
  if (backend.kind === 'down') {
    return (
      <span className="text-bear" title={backend.error}>
        ● Backend: down
      </span>
    )
  }
  return (
    <span className="text-bull">
      ● Backend: up <span className="text-fg-muted">v{backend.version}</span>
    </span>
  )
}

export function TopBar({ backend, theme, onToggleTheme }: Props) {
  return (
    <header className="flex h-11 items-center gap-6 border-b border-border bg-bg-elev px-4">
      <span className="font-semibold tracking-wide">TradeDisha</span>
      <BackendPill backend={backend} />
      <span className="ml-auto" />
      <button
        type="button"
        onClick={onToggleTheme}
        className="rounded border border-border px-2 py-0.5 text-fg-muted hover:text-fg"
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        {theme === 'dark' ? 'Light' : 'Dark'}
      </button>
    </header>
  )
}
