/** 0..1 intensity on a log scale of |ΔOI since open| against the chain's maximum. */
export function oiHeat(chg: number | null, maxAbs: number): number {
  if (chg == null || chg === 0 || maxAbs <= 0) return 0
  return Math.min(1, Math.log1p(Math.abs(chg)) / Math.log1p(maxAbs))
}
