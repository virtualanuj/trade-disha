"""Headlines for the browser (spec §6.7). Pushed over the WebSocket only; no REST route."""

from __future__ import annotations

from tradedisha.api.schemas import HeadlineOut, NewsOut
from tradedisha.app_state import AppState


def news_out(state: AppState) -> NewsOut:
    news = state.news
    return NewsOut(
        status=news.status,
        error=news.error,
        fetched_at=news.fetched_at,
        items=[
            HeadlineOut(
                heading=h.heading,
                summary=h.summary,
                link=h.link,
                published_ts=h.published_ts,
                symbols=list(h.symbols),
            )
            for h in news.items
        ],
        stock_indices={s.symbol: list(s.indices) for s in news.stocks},
    )
