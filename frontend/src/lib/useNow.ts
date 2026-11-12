import { useEffect, useState } from 'react'

/** Wall-clock ms, re-rendered every `everyMs`. For clocks and tick-age displays. */
export function useNow(everyMs = 500): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => {
      setNow(Date.now())
    }, everyMs)
    return () => {
      clearInterval(id)
    }
  }, [everyMs])
  return now
}
