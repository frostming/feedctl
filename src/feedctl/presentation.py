from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from feedctl.models import UnreadArticle


@dataclass(frozen=True, slots=True)
class FeedListItem:
    title: str
    url: str
    error: str | None


def _message(icon: str, icon_style: str, message: str) -> Text:
    text = Text(f"{icon} ", style=icon_style)
    text.append(message)
    return text


def get_console() -> Console:
    return Console(file=sys.stdout, force_terminal=sys.stdout.isatty())


def get_error_console() -> Console:
    return Console(file=sys.stderr, force_terminal=sys.stderr.isatty())


def print_success(message: str) -> None:
    get_console().print(_message("✓", "bold green", message))


def print_error(message: str) -> None:
    get_error_console().print(_message("error:", "bold red", message))


def print_warning(message: str, target: Console | None = None) -> None:
    output = target if target is not None else get_error_console()
    output.print(_message("warning:", "bold yellow", message))


def print_empty(message: str) -> None:
    get_console().print(Text(message, style="dim"))


def _link(url: str) -> Text:
    text = Text(url, style="cyan")
    if url:
        text.stylize(f"link {url}")
    return text


def print_feeds(feeds: list[FeedListItem]) -> None:
    table = Table(
        title=f"Feeds · {len(feeds)}",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Feed", ratio=2)
    table.add_column("URL", ratio=3)
    table.add_column("Status", width=9)

    for feed in feeds:
        if feed.error:
            status = Text("failed", style="bold red")
        else:
            status = Text("ready", style="green")
        table.add_row(Text(feed.title), _link(feed.url), status)
    get_console().print(table)


def print_inbox_table(articles: tuple[UnreadArticle, ...]) -> None:
    table = Table(
        title=f"Inbox · {len(articles)} unread",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Published (UTC)", width=16, no_wrap=True)
    table.add_column("Source", ratio=2)
    table.add_column("Title", ratio=3)
    table.add_column("Link", ratio=3)

    for article in articles:
        published = (
            Text(article.published_at[:16].replace("T", " "))
            if article.published_at
            else Text("—", style="dim")
        )
        table.add_row(
            published,
            Text(article.source),
            Text(article.title),
            _link(article.link),
        )
    get_console().print(table)


def print_inbox_json(articles: tuple[UnreadArticle, ...]) -> None:
    payload = {
        "count": len(articles),
        "articles": [
            {
                "id": article.article_id,
                "source": article.source,
                "title": article.title,
                "url": article.link,
                "published_at": article.published_at,
            }
            for article in articles
        ],
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
