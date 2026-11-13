import type { Banner } from './banner'

export function StatusBanner({ banner }: { banner: Banner | null }) {
  if (!banner) return null
  const tone =
    banner.level === 'error'
      ? 'border-bear/50 bg-bear/15 text-bear'
      : 'border-border bg-bg-elev text-fg-muted'
  return (
    <div
      className={`flex items-center gap-3 border-b px-4 py-1.5 text-xs ${tone}`}
      role={banner.level === 'error' ? 'alert' : 'status'}
      data-testid="status-banner"
    >
      <span>{banner.text}</span>
      {banner.login ? (
        <a
          href="/api/auth/login"
          className="rounded border border-current px-2 py-0.5 font-medium hover:bg-bear/20"
        >
          Login
        </a>
      ) : null}
    </div>
  )
}
