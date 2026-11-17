import type { ReactNode } from 'react'

import { DEFAULT_LAYOUT, LIMITS } from '../../lib/layout'
import { Divider } from '../Divider/Divider'
import { SidePanel } from '../SidePanel/SidePanel'

interface Props {
  /** the option chain's panel; null where there is none (the BULLION tab) */
  chain: ReactNode
  chainMinimised: boolean
  /** the headlines' panel */
  news: ReactNode
  newsMinimised: boolean
  /** headlines taken out of the column */
  newsHidden: boolean
  /** the strip's button: expand the chain and the headlines, and show the headlines */
  onExpandAll: () => void
  /** pixels */
  width: number
  onWidth: (width: number) => void
  /** pixels, while both panels are expanded */
  newsHeight: number
  onNewsHeight: (height: number) => void
  /** classes for the chain's slot: the dimming of stale prices, which headlines do not get */
  chainClassName?: string
}

/**
 * The right-hand column (spec §13.1 "Right column with headlines"): the option chain on
 * top, the headlines below. An expanded panel fills the column unless both are expanded,
 * when a divider sets the headlines' height. With nothing expanded the column is the
 * narrow strip; with neither panel present there is no column.
 */
export function RightColumn({
  chain,
  chainMinimised,
  news,
  newsMinimised,
  newsHidden,
  onExpandAll,
  width,
  onWidth,
  newsHeight,
  onNewsHeight,
  chainClassName = '',
}: Props) {
  const hasChain = chain !== null
  const hasNews = !newsHidden
  if (!hasChain && !hasNews) return null

  const chainOpen = hasChain && !chainMinimised
  const newsOpen = hasNews && !newsMinimised
  const both = chainOpen && newsOpen
  const name = [hasChain ? 'option chain' : null, hasNews ? 'headlines' : null]
    .filter((n) => n !== null)
    .join(' and ')

  if (!chainOpen && !newsOpen) {
    return (
      <SidePanel name={name} open={false} onToggle={onExpandAll} width={width}>
        {null}
      </SidePanel>
    )
  }

  return (
    <>
      <Divider
        orientation="vertical"
        label="Option chain width"
        value={width}
        min={LIMITS.chainMin}
        max={LIMITS.chainMax}
        onDrag={(d) => {
          onWidth(width - d)
        }}
        onReset={() => {
          onWidth(DEFAULT_LAYOUT.chainWidth)
        }}
      />
      <SidePanel name={name} open onToggle={onExpandAll} width={width}>
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          {hasChain ? (
            <div
              className={`${chainOpen ? 'min-h-0 flex-1' : 'shrink-0'} ${chainClassName}`}
              data-testid="right-chain"
              data-fill={chainOpen ? 'true' : undefined}
            >
              {chain}
            </div>
          ) : null}
          {both ? (
            <Divider
              orientation="horizontal"
              label="Headlines height"
              value={newsHeight}
              min={LIMITS.newsMin}
              max={LIMITS.newsMax}
              onDrag={(d) => {
                onNewsHeight(newsHeight - d)
              }}
              onReset={() => {
                onNewsHeight(DEFAULT_LAYOUT.newsHeight)
              }}
            />
          ) : null}
          {hasNews ? (
            <div
              className={newsOpen && !both ? 'min-h-0 flex-1' : 'shrink-0'}
              style={both ? { height: newsHeight, maxHeight: '70%' } : undefined}
              data-testid="right-news"
              data-fill={newsOpen && !both ? 'true' : undefined}
            >
              {news}
            </div>
          ) : null}
        </div>
      </SidePanel>
    </>
  )
}
