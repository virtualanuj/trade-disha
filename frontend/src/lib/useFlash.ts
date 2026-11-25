import { useEffect, useRef, useState } from 'react'

/** 'up' or 'down' for 150 ms after the value rises or falls: the price tick flash. */
export function useFlash(value: number | null): 'up' | 'down' | null {
  const prev = useRef<number | null>(null)
  const [dir, setDir] = useState<'up' | 'down' | null>(null)
  useEffect(() => {
    const p = prev.current
    prev.current = value
    if (value == null || p == null) {
      // the cleanup just cleared the reset timer of a flash in progress: end it here
      setDir(null)
      return
    }
    if (value === p) return
    setDir(value > p ? 'up' : 'down')
    const id = setTimeout(() => {
      setDir(null)
    }, 150)
    return () => {
      clearTimeout(id)
    }
  }, [value])
  return dir
}
