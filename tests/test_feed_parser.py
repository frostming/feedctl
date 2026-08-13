from __future__ import annotations

import unittest

from feedctl.feed_parser import FeedParseError, parse_feed


RSS = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example RSS</title>
    <item>
      <guid>article-1</guid>
      <title>First article</title>
      <link>https://example.com/first</link>
      <pubDate>Wed, 12 Aug 2026 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <id>tag:example.com,2026:second</id>
    <title>Second article</title>
    <link rel="alternate" href="https://example.com/second" />
    <updated>2026-08-13T08:30:00Z</updated>
  </entry>
</feed>
"""


class FeedParserTests(unittest.TestCase):
    def test_parses_rss(self) -> None:
        feed = parse_feed(RSS, "Fallback")

        self.assertEqual(feed.title, "Example RSS")
        self.assertEqual(len(feed.entries), 1)
        self.assertEqual(feed.entries[0].external_id, "article-1")
        self.assertEqual(feed.entries[0].published_at, "2026-08-12T10:00:00+00:00")

    def test_parses_namespaced_atom(self) -> None:
        feed = parse_feed(ATOM, "Fallback")

        self.assertEqual(feed.title, "Example Atom")
        self.assertEqual(feed.entries[0].link, "https://example.com/second")
        self.assertEqual(feed.entries[0].published_at, "2026-08-13T08:30:00+00:00")

    def test_rejects_unknown_document(self) -> None:
        with self.assertRaises(FeedParseError):
            parse_feed(b"<html />", "Fallback")


if __name__ == "__main__":
    unittest.main()
