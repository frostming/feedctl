from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeedEntry:
    external_id: str
    title: str
    link: str
    published_at: str | None


@dataclass(frozen=True, slots=True)
class ParsedFeed:
    title: str
    entries: tuple[FeedEntry, ...]


@dataclass(frozen=True, slots=True)
class UnreadArticle:
    article_id: int
    source: str
    title: str
    link: str
