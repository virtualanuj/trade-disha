import { usePref } from './usePref'

const METAL_KEY = 'tradedisha.bullionChart'

/** The metal the BULLION tab's panels follow, remembered in this browser. */
export function useBullionMetal(names: string[]): [string, (metal: string) => void] {
  const [stored, setMetal] = usePref(METAL_KEY, (v) => (typeof v === 'string' ? v : 'GOLD'))
  const metal = names.includes(stored) ? stored : (names[0] ?? 'GOLD')
  return [metal, setMetal]
}
