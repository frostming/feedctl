from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from feedctl.models import FeedEntry, ParsedFeed
from feedctl.store import Store


class StoreTests(unittest.TestCase):
    def test_unread_listing_and_selective_read_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "feedctl.db"
            with Store(database) as store:
                self.assertTrue(
                    store.add_feed("https://example.com/feed.xml", "Example")
                )
                feed_id = store.list_feeds()[0]["id"]
                store.sync_feed(
                    feed_id,
                    ParsedFeed(
                        title="Example",
                        entries=(
                            FeedEntry(
                                external_id="article-1",
                                title="Original title",
                                link="https://example.com/article-1",
                                published_at="2026-08-13T08:00:00+00:00",
                            ),
                            FeedEntry(
                                external_id="article-2",
                                title="Second title",
                                link="https://example.com/article-2",
                                published_at="2026-08-13T09:00:00+00:00",
                            ),
                        ),
                    ),
                    etag=None,
                    last_modified=None,
                )

                first_listing = store.list_unread()
                self.assertEqual(store.list_unread(), first_listing)
                self.assertEqual(len(first_listing), 2)

                selected_id = first_listing[0].article_id
                self.assertEqual(store.mark_read([selected_id, selected_id]), 1)
                self.assertEqual(len(store.list_unread()), 1)
                self.assertEqual(store.mark_read([selected_id]), 0)

                self.assertEqual(store.mark_read(), 1)
                self.assertEqual(store.list_unread(), ())

    def test_import_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with Store(Path(directory) / "feedctl.db") as store:
                feeds = (("https://example.com/feed.xml", "Example"),)
                self.assertEqual(store.import_feeds(feeds), 1)
                self.assertEqual(store.import_feeds(feeds), 0)


if __name__ == "__main__":
    unittest.main()
