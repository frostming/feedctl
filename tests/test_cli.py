from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from feedctl.cli import build_parser, run
from feedctl.fetcher import FetchResult
from feedctl.store import Store


RSS = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example RSS</title>
    <item>
      <guid>article-1</guid>
      <title>First article</title>
      <link>https://example.com/first</link>
      <pubDate>Wed, 12 Aug 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <guid>article-2</guid>
      <title>Second article</title>
      <link>https://example.com/second</link>
      <pubDate>Wed, 12 Aug 2026 11:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

UNTITLED_RSS = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <guid>article-1</guid>
      <title>First article</title>
      <link>https://example.com/first</link>
    </item>
  </channel>
</rss>
"""


class CliTests(unittest.TestCase):
    def test_inbox_is_repeatable_and_read_marks_selected_or_all(self) -> None:
        parser = build_parser()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "feedctl.db"
            add_args = parser.parse_args(
                ["--database", str(database), "add", "https://example.com/feed.xml"]
            )
            with (
                patch(
                    "feedctl.cli.fetch_feed",
                    return_value=FetchResult(
                        data=RSS, etag='"feed-v1"', last_modified="yesterday"
                    ),
                ),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(run(add_args), 0)

            with Store(database) as store:
                feed = store.list_feeds()[0]
                self.assertEqual(feed["title"], "Example RSS")
                self.assertEqual(feed["etag"], '"feed-v1"')
                self.assertEqual(len(store.list_unread()), 2)

            inbox_args = parser.parse_args(
                ["--database", str(database), "inbox", "--format", "json"]
            )
            inbox_stdout = io.StringIO()
            with (
                patch(
                    "feedctl.cli.fetch_feed",
                    return_value=FetchResult(
                        data=RSS, etag='"feed-v1"', last_modified=None
                    ),
                ),
                redirect_stdout(inbox_stdout),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(run(inbox_args), 0)

            inbox = json.loads(inbox_stdout.getvalue())
            article_ids = [article["id"] for article in inbox["articles"]]
            self.assertEqual(inbox["count"], 2)
            self.assertEqual(len(article_ids), 2)
            self.assertEqual(
                [article["published_at"] for article in inbox["articles"]],
                [
                    "2026-08-12T11:00:00+00:00",
                    "2026-08-12T10:00:00+00:00",
                ],
            )

            repeated_stdout = io.StringIO()
            with (
                patch(
                    "feedctl.cli.fetch_feed",
                    return_value=FetchResult(
                        data=None, etag='"feed-v1"', last_modified=None
                    ),
                ),
                redirect_stdout(repeated_stdout),
            ):
                self.assertEqual(run(inbox_args), 0)
            self.assertEqual(repeated_stdout.getvalue(), inbox_stdout.getvalue())

            read_one_args = parser.parse_args(
                ["--database", str(database), "read", str(article_ids[0])]
            )
            read_stdout = io.StringIO()
            with (
                patch("feedctl.cli.fetch_feed", side_effect=AssertionError),
                redirect_stdout(read_stdout),
            ):
                self.assertEqual(run(read_one_args), 0)
            self.assertIn("Marked 1 article(s) as read", read_stdout.getvalue())

            read_all_args = parser.parse_args(["--database", str(database), "read"])
            read_all_stdout = io.StringIO()
            with redirect_stdout(read_all_stdout), redirect_stderr(io.StringIO()):
                self.assertEqual(run(read_all_args), 0)

            empty_inbox_stdout = io.StringIO()
            with (
                patch(
                    "feedctl.cli.fetch_feed",
                    return_value=FetchResult(
                        data=None, etag='"feed-v1"', last_modified=None
                    ),
                ),
                redirect_stdout(empty_inbox_stdout),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(run(inbox_args), 0)

        self.assertIn("Marked 1 article(s) as read", read_all_stdout.getvalue())
        self.assertEqual(
            json.loads(empty_inbox_stdout.getvalue()),
            {"count": 0, "articles": []},
        )

    def test_add_rejects_a_feed_without_a_title(self) -> None:
        parser = build_parser()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "feedctl.db"
            args = parser.parse_args(
                ["--database", str(database), "add", "https://example.com/feed.xml"]
            )
            stderr = io.StringIO()
            with (
                patch(
                    "feedctl.cli.fetch_feed",
                    return_value=FetchResult(
                        data=UNTITLED_RSS, etag=None, last_modified=None
                    ),
                ),
                redirect_stderr(stderr),
            ):
                self.assertEqual(run(args), 2)

            with Store(database) as store:
                self.assertEqual(store.list_feeds(), [])

        self.assertIn("feed has no title", stderr.getvalue())

    def test_inbox_shows_progress_on_an_interactive_terminal(self) -> None:
        parser = build_parser()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "feedctl.db"
            with Store(database) as store:
                store.add_feed("https://example.com/feed.xml")

            args = parser.parse_args(["--database", str(database), "inbox"])
            progress_output = io.StringIO()
            terminal_console = Console(
                file=progress_output,
                force_terminal=True,
                no_color=True,
            )
            inbox_stdout = io.StringIO()
            with (
                patch(
                    "feedctl.cli.fetch_feed",
                    return_value=FetchResult(
                        data=RSS, etag='"feed-v1"', last_modified=None
                    ),
                ),
                patch(
                    "feedctl.cli.get_error_console", return_value=terminal_console
                ),
                redirect_stdout(inbox_stdout),
            ):
                self.assertEqual(run(args), 0)

        self.assertIn("Refreshing feeds", progress_output.getvalue())
        self.assertIn("Inbox · 2 unread", inbox_stdout.getvalue())
        self.assertIn("Example RSS", inbox_stdout.getvalue())
        self.assertIn("Published (UTC)", inbox_stdout.getvalue())
        self.assertIn("2026-08-12 11:00", inbox_stdout.getvalue())
        self.assertNotIn("ID", inbox_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
