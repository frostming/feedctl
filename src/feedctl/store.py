from __future__ import annotations

import sqlite3
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Self

from feedctl.models import ParsedFeed, UnreadArticle

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    added_at TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    published_at TEXT,
    discovered_at TEXT NOT NULL,
    read_at TEXT,
    UNIQUE(feed_id, external_id)
);

CREATE INDEX IF NOT EXISTS articles_unread_idx
ON articles(read_at, published_at DESC);

"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        return self

    def __exit__(self, *_: object) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("store is not open")
        return self.connection

    @contextmanager
    def immediate_transaction(self) -> Generator[None, None, None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def feed_exists(self, url: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM feeds WHERE url = ? LIMIT 1", (url,)
        ).fetchone()
        return row is not None

    def add_feed(
        self,
        url: str,
        title: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> int | None:
        cursor = self.db.execute(
            """
            INSERT OR IGNORE INTO feeds(
                url, title, added_at, etag, last_modified
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (url, title or url, _now(), etag, last_modified),
        )
        self.db.commit()
        if cursor.rowcount != 1:
            return None
        return cursor.lastrowid

    def import_feeds(self, feeds: tuple[tuple[str, str], ...]) -> int:
        added = 0
        with self.immediate_transaction():
            for url, title in feeds:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO feeds(url, title, added_at) VALUES (?, ?, ?)",
                    (url, title or url, _now()),
                )
                added += cursor.rowcount
        return added

    def remove_feed(self, url: str) -> bool:
        cursor = self.db.execute("DELETE FROM feeds WHERE url = ?", (url,))
        self.db.commit()
        return cursor.rowcount == 1

    def list_feeds(self) -> list[sqlite3.Row]:
        return list(
            self.db.execute("SELECT * FROM feeds ORDER BY title COLLATE NOCASE, url")
        )

    def sync_feed(
        self,
        feed_id: int,
        parsed: ParsedFeed,
        etag: str | None,
        last_modified: str | None,
    ) -> int:
        discovered_at = _now()
        inserted = 0
        with self.immediate_transaction():
            self.db.execute(
                """
                UPDATE feeds
                SET title = ?, etag = ?, last_modified = ?, last_error = NULL
                WHERE id = ?
                """,
                (parsed.title, etag, last_modified, feed_id),
            )
            for entry in parsed.entries:
                cursor = self.db.execute(
                    """
                    INSERT INTO articles(
                        feed_id, external_id, title, link, published_at, discovered_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(feed_id, external_id) DO UPDATE SET
                        title = excluded.title,
                        link = excluded.link,
                        published_at = COALESCE(excluded.published_at, articles.published_at)
                    """,
                    (
                        feed_id,
                        entry.external_id,
                        entry.title,
                        entry.link,
                        entry.published_at,
                        discovered_at,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def record_feed_error(self, feed_id: int, message: str) -> None:
        self.db.execute(
            "UPDATE feeds SET last_error = ? WHERE id = ?", (message, feed_id)
        )
        self.db.commit()

    def list_unread(self) -> tuple[UnreadArticle, ...]:
        rows = self.db.execute(
            """
            SELECT articles.id, feeds.title AS source, articles.title, articles.link
            FROM articles
            JOIN feeds ON feeds.id = articles.feed_id
            WHERE articles.read_at IS NULL
            ORDER BY COALESCE(articles.published_at, articles.discovered_at) DESC,
                     articles.id DESC
            """
        )
        return tuple(
            UnreadArticle(
                article_id=row["id"],
                source=row["source"],
                title=row["title"],
                link=row["link"],
            )
            for row in rows
        )

    def mark_read(self, article_ids: Iterable[int] | None = None) -> int:
        selected_ids = None
        if article_ids is not None:
            selected_ids = tuple(dict.fromkeys(article_ids))
            if not selected_ids:
                return 0

        with self.immediate_transaction():
            where_clause = "read_at IS NULL"
            parameters: tuple[int, ...] = ()
            if selected_ids is not None:
                placeholders = ", ".join("?" for _ in selected_ids)
                where_clause += f" AND id IN ({placeholders})"
                parameters = selected_ids

            cursor = self.db.execute(
                f"UPDATE articles SET read_at = ? WHERE {where_clause}",
                (_now(), *parameters),
            )
        return cursor.rowcount
