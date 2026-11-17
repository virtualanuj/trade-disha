import { useState } from 'react'

import type { HeadlineOut, NewsOut } from '../../api/types'
import {
  chipKind,
  fmtNewsClock,
  freshness,
  groupByDay,
  newsStatusText,
  safeLink,
} from '../../lib/news'
import type { ChipKind, Freshness } from '../../lib/news'

interface Props {
  news: NewsOut | null
  /** time of the newest headline the trader has seen; newer ones are marked unseen */
  seenTs: number | null
  now: number
}

/** time label: accent within the hour, plain today, muted before */
const TIME_CLS: Record<Freshness, string> = {
  hour: 'text-accent',
  today: 'text-fg',
  older: 'text-fg-muted',
}

/** a stock's chip by the index it moves; never green or red, which mean bull and bear */
const CHIP_CLS: Record<ChipKind, string> = {
  bank: 'bg-index-bank/15 text-index-bank',
  nifty: 'bg-fg/10 text-fg',
  other: 'bg-bg-row text-fg-muted',
}

const CHIP_TITLE: Record<ChipKind, (indices: string[]) => string> = {
  bank: (indices) => (indices.includes('NIFTY') ? 'In NIFTY and BANK NIFTY' : 'In BANK NIFTY'),
  nifty: () => 'In NIFTY',
  other: () => 'Not in the index list',
}

interface RowProps {
  h: HeadlineOut
  unseen: boolean
  now: number
  stockIndices: Record<string, string[]>
}

function Row({ h, unseen, now, stockIndices }: RowProps) {
  const [open, setOpen] = useState(false)
  const href = safeLink(h.link)
  const fresh = freshness(h.published_ts, now)
  return (
    <li
      className={`border-b border-l-2 border-b-border/40 py-2 pr-3 pl-2.5 last:border-b-0 ${
        unseen ? 'border-l-accent' : 'border-l-transparent'
      }`}
      data-testid="headline"
      data-new={unseen ? 'true' : undefined}
      data-fresh={fresh}
      title={unseen ? 'New since you last looked' : undefined}
    >
      <div className="flex items-center gap-2 text-[11px]">
        <span className={`shrink-0 font-mono ${TIME_CLS[fresh]}`}>
          {fmtNewsClock(h.published_ts)}
        </span>
        <span className="flex min-w-0 flex-wrap gap-1">
          {h.symbols.map((s) => {
            const kind = chipKind(s, stockIndices)
            return (
              <span
                key={s}
                className={`rounded px-1 font-mono text-[10px] ${CHIP_CLS[kind]}`}
                data-kind={kind}
                title={CHIP_TITLE[kind](stockIndices[s] ?? [])}
              >
                {s}
              </span>
            )
          })}
        </span>
        {h.summary ? (
          <button
            type="button"
            className="ml-auto flex h-5 w-5 shrink-0 items-center justify-center rounded text-fg-muted hover:bg-bg-row hover:text-fg"
            aria-expanded={open}
            aria-label={open ? 'Hide summary' : 'Show summary'}
            title={open ? 'Hide summary' : 'Show summary'}
            onClick={() => {
              setOpen(!open)
            }}
          >
            <span aria-hidden="true">{open ? '▾' : '▸'}</span>
          </button>
        ) : null}
      </div>
      <div
        className={`mt-0.5 text-xs leading-snug break-words ${
          fresh === 'older' ? 'text-fg-muted' : 'text-fg'
        }`}
      >
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-accent hover:underline"
          >
            {h.heading}
          </a>
        ) : (
          <span>{h.heading}</span>
        )}
      </div>
      {open && h.summary ? (
        <p className="mt-1 text-xs leading-snug break-words text-fg-muted">{h.summary}</p>
      ) : null}
    </li>
  )
}

/**
 * Upstox headlines for the heaviest index stocks, newest first and grouped by IST day
 * (spec §6.7, §13.2). Display only. Colour says how fresh a story is and which index its
 * stocks move. An error or an expired login keeps the last list with a note above it.
 */
export function Headlines({ news, seenTs, now }: Props) {
  const items = news?.items ?? []
  const stockIndices = news?.stock_indices ?? {}
  const note = newsStatusText(news)
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="headlines">
      {note ? (
        <div
          className={`shrink-0 px-3 py-2 text-xs text-fg-muted ${
            items.length > 0 ? 'border-b border-border/40' : ''
          }`}
        >
          {note}
        </div>
      ) : null}
      {items.length > 0 ? (
        <div className="min-h-0 flex-1 overflow-auto">
          {groupByDay(items, now).map((g) => (
            <section key={g.label} data-testid="headline-day" data-day={g.label}>
              <h3
                className={`sticky top-0 z-10 border-b border-border/60 bg-bg-elev px-3 py-1 text-[10px] tracking-wide uppercase ${
                  g.today ? 'text-fg' : 'text-fg-muted'
                }`}
              >
                {g.label}
              </h3>
              <ul>
                {g.items.map((h) => (
                  <Row
                    key={h.link ?? h.heading}
                    h={h}
                    unseen={seenTs != null && h.published_ts > seenTs}
                    now={now}
                    stockIndices={stockIndices}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : null}
    </div>
  )
}
