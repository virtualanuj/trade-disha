import type { Banner } from './banner'

/**
 * One band under the top bar. Errors are red; a market's session state (closed, holiday,
 * pre-open) is amber with a bold title, so a closed market is never mistaken for a quiet one.
 */
export function StatusBanner({ banner }: { banner: Banner | null }) {
  if (!banner) return null
  const error = banner.level === 'error'
  const tone = error ? 'border-bear/60 bg-bear/15 text-bear' : 'border-warn/60 bg-warn/15 text-warn'
  return (
    <div
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 border-b-2 px-4 py-2.5 text-sm ${tone}`}
      role={error ? 'alert' : 'status'}
      data-testid="status-banner"
    >
      <span aria-hidden="true" className="text-base leading-none">
        {error ? '⚠' : '⏸'}
      </span>
      {banner.title ? (
        <span className="font-semibold uppercase tracking-wide">{banner.title}</span>
      ) : null}
      <span className={banner.title ? 'text-fg' : undefined}>{banner.text}</span>
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
