from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from feedctl.models import FeedEntry, ParsedFeed


class FeedParseError(ValueError):
    pass


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next(iter(_children(element, name)), None)


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _normalize_date(value: str) -> str | None:
    if not value:
        return None

    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        pass

    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _entry_id(given_id: str, link: str, title: str, published_at: str | None) -> str:
    if given_id:
        return given_id
    if link:
        return link
    material = "\x00".join((title, published_at or ""))
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


def _parse_rss(root: ElementTree.Element, fallback_title: str) -> ParsedFeed:
    channel = _child(root, "channel")
    if channel is None:
        raise FeedParseError("RSS document has no channel")

    title = _text(_child(channel, "title")) or fallback_title
    entries: list[FeedEntry] = []
    for item in _children(channel, "item"):
        item_title = _text(_child(item, "title")) or "(untitled)"
        link = _text(_child(item, "link"))
        published_at = _normalize_date(
            _text(_child(item, "pubDate")) or _text(_child(item, "date"))
        )
        given_id = _text(_child(item, "guid"))
        entries.append(
            FeedEntry(
                external_id=_entry_id(given_id, link, item_title, published_at),
                title=item_title,
                link=link,
                published_at=published_at,
            )
        )
    return ParsedFeed(title=title, entries=tuple(entries))


def _atom_link(entry: ElementTree.Element) -> str:
    fallback = ""
    for link in _children(entry, "link"):
        href = link.attrib.get("href", "").strip()
        if not href:
            continue
        fallback = fallback or href
        if link.attrib.get("rel", "alternate") == "alternate":
            return href
    return fallback


def _parse_atom(root: ElementTree.Element, fallback_title: str) -> ParsedFeed:
    title = _text(_child(root, "title")) or fallback_title
    entries: list[FeedEntry] = []
    for entry in _children(root, "entry"):
        entry_title = _text(_child(entry, "title")) or "(untitled)"
        link = _atom_link(entry)
        published_at = _normalize_date(
            _text(_child(entry, "published")) or _text(_child(entry, "updated"))
        )
        given_id = _text(_child(entry, "id"))
        entries.append(
            FeedEntry(
                external_id=_entry_id(given_id, link, entry_title, published_at),
                title=entry_title,
                link=link,
                published_at=published_at,
            )
        )
    return ParsedFeed(title=title, entries=tuple(entries))


def parse_feed(data: bytes, fallback_title: str) -> ParsedFeed:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise FeedParseError(f"invalid XML: {error}") from error

    root_name = _local_name(root.tag).lower()
    if root_name in {"rss", "rdf"}:
        if root_name == "rdf":
            channel = _child(root, "channel")
            if channel is None:
                raise FeedParseError("RDF document has no channel")
            synthetic = ElementTree.Element("rss")
            synthetic_channel = ElementTree.SubElement(synthetic, "channel")
            for child in channel:
                synthetic_channel.append(child)
            for item in _children(root, "item"):
                synthetic_channel.append(item)
            root = synthetic
        return _parse_rss(root, fallback_title)
    if root_name == "feed":
        return _parse_atom(root, fallback_title)
    raise FeedParseError(f"unsupported feed root element: {root_name}")
