from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


class OpmlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OpmlFeed:
    url: str
    title: str


def parse_opml(path: Path) -> tuple[OpmlFeed, ...]:
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError) as error:
        raise OpmlError(str(error)) from error

    if root.tag.rsplit("}", 1)[-1].lower() != "opml":
        raise OpmlError("document is not OPML")

    feeds: list[OpmlFeed] = []
    seen: set[str] = set()
    for outline in root.iter():
        if outline.tag.rsplit("}", 1)[-1] != "outline":
            continue
        url = (
            outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl") or ""
        ).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = (
            outline.attrib.get("title") or outline.attrib.get("text") or url
        ).strip()
        feeds.append(OpmlFeed(url=url, title=title))
    return tuple(feeds)


def render_opml(feeds: list[tuple[str, str]]) -> bytes:
    root = ElementTree.Element("opml", {"version": "2.0"})
    head = ElementTree.SubElement(root, "head")
    ElementTree.SubElement(head, "title").text = "feedctl subscriptions"
    ElementTree.SubElement(head, "dateCreated").text = datetime.now(
        timezone.utc
    ).strftime("%a, %d %b %Y %H:%M:%S +0000")
    body = ElementTree.SubElement(root, "body")
    for title, url in feeds:
        ElementTree.SubElement(
            body,
            "outline",
            {"type": "rss", "text": title, "title": title, "xmlUrl": url},
        )
    ElementTree.indent(root, space="  ")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
