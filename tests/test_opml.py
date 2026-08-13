from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from feedctl.opml import parse_opml, render_opml


class OpmlTests(unittest.TestCase):
    def test_nested_import_deduplicates_urls(self) -> None:
        document = b"""<?xml version="1.0"?>
<opml version="2.0">
  <body>
    <outline text="Folder">
      <outline text="Example" xmlUrl="https://example.com/feed.xml" />
      <outline text="Duplicate" xmlUrl="https://example.com/feed.xml" />
    </outline>
  </body>
</opml>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feeds.opml"
            path.write_bytes(document)

            feeds = parse_opml(path)

        self.assertEqual(len(feeds), 1)
        self.assertEqual(feeds[0].title, "Example")

    def test_export_round_trip(self) -> None:
        document = render_opml([("A & B", "https://example.com/feed?a=1&b=2")])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feeds.opml"
            path.write_bytes(document)
            feeds = parse_opml(path)

        self.assertEqual(feeds[0].title, "A & B")
        self.assertEqual(feeds[0].url, "https://example.com/feed?a=1&b=2")


if __name__ == "__main__":
    unittest.main()
