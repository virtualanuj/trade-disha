import { useCallback, useState } from 'react'

function read<T>(key: string, parse: (v: unknown) => T): T {
  try {
    const raw = localStorage.getItem(key)
    return parse(raw == null ? undefined : (JSON.parse(raw) as unknown))
  } catch {
    return parse(undefined)
  }
}

/**
 * A preference remembered in this browser. `parse` turns whatever was stored (or
 * `undefined`) into a valid value, so a missing or damaged entry falls back cleanly.
 */
export function usePref<T>(key: string, parse: (v: unknown) => T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => read(key, parse))
  const set = useCallback(
    (next: T) => {
      setValue(next)
      try {
        localStorage.setItem(key, JSON.stringify(next))
      } catch {
        // storage unavailable; the choice still holds for this page load
      }
    },
    [key],
  )
  return [value, set]
}
