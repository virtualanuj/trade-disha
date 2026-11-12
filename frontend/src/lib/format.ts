const inr = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const istClock = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export function fmtPrice(v: number | null | undefined): string {
  return v == null ? '—' : inr.format(v)
}

export function fmtIstTime(ms: number): string {
  return istClock.format(new Date(ms))
}

export function fmtAge(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${String(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function fmtMs(v: number): string {
  return v >= 100 ? v.toFixed(0) : v.toFixed(1)
}

/** Tailwind colour class for a tick age: green under 2 s, amber under 10 s, red beyond. */
export function tickAgeColour(ageMs: number | null): string {
  if (ageMs == null) return 'text-fg-muted'
  if (ageMs < 2000) return 'text-bull'
  if (ageMs < 10_000) return 'text-warn'
  return 'text-bear'
}

const compact = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 })

/** Open interest in lakh/crore-style compact form: 12.3L, 1.2Cr. */
export function fmtOi(v: number | null | undefined): string {
  if (v == null) return '—'
  const a = Math.abs(v)
  if (a >= 1e7) return `${(v / 1e7).toFixed(2)}Cr`
  if (a >= 1e5) return `${(v / 1e5).toFixed(1)}L`
  return compact.format(v)
}

export function fmtSigned(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—'
  const s = v.toFixed(digits)
  return v > 0 ? `+${s}` : s
}
