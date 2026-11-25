import { useCallback, useState } from 'react'

export interface InFlight {
  /** ids whose request has not answered yet */
  busy: ReadonlySet<string>
  /** the server's reason, by id, for requests it refused; cleared when that id is retried */
  errors: Readonly<Record<string, string>>
  /** send `request` for `id`; `fallback` is the reason shown for an error without a message */
  run: (id: string, request: () => Promise<unknown>, fallback: string) => void
}

function without(errors: Readonly<Record<string, string>>, id: string): Record<string, string> {
  return Object.fromEntries(Object.entries(errors).filter(([k]) => k !== id))
}

/**
 * Requests in flight and their refusals, each kept by its own id (a trade, a signal), so
 * one row's answer never re-enables another row's button or replaces its error.
 */
export function useInFlight(): InFlight {
  const [busy, setBusy] = useState<ReadonlySet<string>>(() => new Set())
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({})
  const run = useCallback((id: string, request: () => Promise<unknown>, fallback: string) => {
    setBusy((b) => new Set(b).add(id))
    setErrors((e) => without(e, id))
    request()
      .catch((err: unknown) => {
        setErrors((e) => ({ ...e, [id]: err instanceof Error ? err.message : fallback }))
      })
      .finally(() => {
        setBusy((b) => new Set([...b].filter((x) => x !== id)))
      })
  }, [])
  return { busy, errors, run }
}
