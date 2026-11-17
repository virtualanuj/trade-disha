/** Sizes of the resizable panels, in pixels. */
export interface Layout {
  /** width of the right-hand column (option chain and headlines) */
  chainWidth: number
  /** height of the price chart */
  chartHeight: number
  /** height of the headlines under the option chain (E10) */
  newsHeight: number
}

export const DEFAULT_LAYOUT: Layout = { chainWidth: 640, chartHeight: 320, newsHeight: 280 }

export const LIMITS = {
  chainMin: 420,
  chainMax: 900,
  /** the chain panel never takes more than this share of the window */
  chainShare: 0.6,
  chartMin: 200,
  chartMax: 700,
  newsMin: 120,
  newsMax: 900,
} as const

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), Math.max(lo, hi))
}

/**
 * A layout that fits the window. Applied on load, on every drag and on window resize, so
 * sizes saved on a large screen cannot hide a panel on a small one.
 */
export function clampLayout(l: Layout, windowWidth: number): Layout {
  const chainMax = Math.min(LIMITS.chainMax, Math.floor(windowWidth * LIMITS.chainShare))
  return {
    chainWidth: Math.round(clamp(l.chainWidth, LIMITS.chainMin, chainMax)),
    chartHeight: Math.round(clamp(l.chartHeight, LIMITS.chartMin, LIMITS.chartMax)),
    newsHeight: Math.round(clamp(l.newsHeight, LIMITS.newsMin, LIMITS.newsMax)),
  }
}

function isSize(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/**
 * A stored layout, if it is one; anything else falls back to the default. A layout stored
 * before E10 has no headlines height and gets the default one.
 */
export function parseLayout(v: unknown): Layout {
  if (typeof v === 'object' && v !== null) {
    const { chainWidth, chartHeight, newsHeight } = v as Record<string, unknown>
    if (isSize(chainWidth) && isSize(chartHeight)) {
      return {
        chainWidth,
        chartHeight,
        newsHeight: isSize(newsHeight) ? newsHeight : DEFAULT_LAYOUT.newsHeight,
      }
    }
  }
  return DEFAULT_LAYOUT
}
