from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from feedctl.feed_parser import FeedParseError, parse_feed
from feedctl.fetcher import FetchError, fetch_feed
from feedctl.models import ParsedFeed
from feedctl.opml import OpmlError, parse_opml, render_opml
from feedctl.presentation import (
    FeedListItem,
    get_error_console,
    print_empty,
    print_error,
    print_feeds,
    print_inbox_json,
    print_inbox_table,
    print_success,
    print_warning,
)
from feedctl.store import Store


@dataclass(frozen=True, slots=True)
class FeedSource:
    feed_id: int
    url: str
    title: str
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    source: FeedSource
    parsed: ParsedFeed | None
    etag: str | None
    last_modified: str | None
    error: str | None


def default_database_path() -> Path:
    configured = os.environ.get("FEEDCTL_DB")
    if configured:
        return Path(configured).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "feedctl" / "feedctl.db"


def _feed_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("feed URL must use http:// or https://")
    return value


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("article ID must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("article ID must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feedctl", description="Manage RSS and Atom feeds"
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=default_database_path(),
        help="SQLite database path (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="add a feed")
    add_parser.add_argument("url", type=_feed_url)

    remove_parser = subparsers.add_parser(
        "remove", help="remove a feed and its articles"
    )
    remove_parser.add_argument("url", type=_feed_url)

    import_parser = subparsers.add_parser("import", help="import feeds from OPML")
    import_parser.add_argument("opml", type=Path)

    export_parser = subparsers.add_parser("export", help="export feeds as OPML")
    export_parser.add_argument(
        "--output", "-o", type=Path, help="write to a file instead of stdout"
    )

    inbox_parser = subparsers.add_parser("inbox", help="fetch and list unread articles")
    inbox_parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output format (default: %(default)s)",
    )

    read_parser = subparsers.add_parser("read", help="mark articles as read")
    read_parser.add_argument(
        "article_ids",
        nargs="*",
        type=_positive_int,
        metavar="ARTICLE_ID",
        help="articles to mark (default: all unread articles)",
    )
    subparsers.add_parser("list", help="list subscribed feeds")

    return parser


def _load_feed(source: FeedSource) -> RefreshOutcome:
    try:
        result = fetch_feed(
            source.url,
            etag=source.etag,
            last_modified=source.last_modified,
        )
        parsed = None if result.data is None else parse_feed(result.data, source.title)
        return RefreshOutcome(
            source=source,
            parsed=parsed,
            etag=result.etag,
            last_modified=result.last_modified,
            error=None,
        )
    except (FetchError, FeedParseError) as error:
        return RefreshOutcome(
            source=source,
            parsed=None,
            etag=source.etag,
            last_modified=source.last_modified,
            error=str(error),
        )


def _refresh(store: Store) -> int:
    sources = [
        FeedSource(
            feed_id=feed["id"],
            url=feed["url"],
            title=feed["title"],
            etag=feed["etag"],
            last_modified=feed["last_modified"],
        )
        for feed in store.list_feeds()
    ]
    if not sources:
        return 0

    failures = 0
    progress_console = get_error_console()
    progress = Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=progress_console,
        transient=True,
        disable=not progress_console.is_terminal,
    )
    with (
        ThreadPoolExecutor(max_workers=min(8, len(sources))) as executor,
        progress,
    ):
        task_id = progress.add_task("Refreshing feeds", total=len(sources))
        futures = [executor.submit(_load_feed, source) for source in sources]
        for future in as_completed(futures):
            outcome = future.result()
            try:
                if outcome.error is not None:
                    failures += 1
                    store.record_feed_error(outcome.source.feed_id, outcome.error)
                    print_warning(
                        f"failed to refresh {outcome.source.url}: {outcome.error}",
                        target=progress_console,
                    )
                    continue
                if outcome.parsed is None:
                    continue
                store.sync_feed(
                    outcome.source.feed_id,
                    outcome.parsed,
                    outcome.etag,
                    outcome.last_modified,
                )
            finally:
                progress.advance(task_id)
    return failures


def run(args: argparse.Namespace) -> int:
    with Store(args.database) as store:
        if args.command == "add":
            if store.feed_exists(args.url):
                print_error(f"Feed already exists: {args.url}")
                return 1

            progress_console = get_error_console()
            status = (
                progress_console.status("[bold blue]Fetching feed")
                if progress_console.is_terminal
                else nullcontext()
            )
            try:
                with status:
                    result = fetch_feed(args.url)
                    if result.data is None:
                        raise FetchError("feed returned no content")
                    parsed = parse_feed(result.data, "")
                    if not parsed.title:
                        raise FeedParseError("feed has no title")
            except (FetchError, FeedParseError) as error:
                print_error(f"Cannot add feed {args.url}: {error}")
                return 2

            feed_id = store.add_feed(
                args.url,
                parsed.title,
                etag=result.etag,
                last_modified=result.last_modified,
            )
            if feed_id is None:
                print_error(f"Feed already exists: {args.url}")
                return 1
            store.sync_feed(
                feed_id,
                parsed,
                result.etag,
                result.last_modified,
            )
            print_success(f"Added {parsed.title} ({args.url})")
            return 0

        if args.command == "remove":
            if not store.remove_feed(args.url):
                print_error(f"Feed not found: {args.url}")
                return 1
            print_success(f"Removed {args.url}")
            return 0

        if args.command == "import":
            try:
                feeds = parse_opml(args.opml)
            except OpmlError as error:
                print_error(f"Cannot import OPML: {error}")
                return 2
            added = store.import_feeds(tuple((feed.url, feed.title) for feed in feeds))
            print_success(
                f"Imported {added} feed(s); {len(feeds) - added} already existed"
            )
            return 0

        if args.command == "export":
            feeds = [(row["title"], row["url"]) for row in store.list_feeds()]
            document = render_opml(feeds)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(document)
                print_success(f"Exported {len(feeds)} feed(s) to {args.output}")
            else:
                sys.stdout.write(document.decode("utf-8"))
            return 0

        if args.command == "list":
            feeds = store.list_feeds()
            if not feeds:
                print_empty("No feeds configured.")
                return 0
            print_feeds(
                [
                    FeedListItem(
                        title=feed["title"],
                        url=feed["url"],
                        error=feed["last_error"],
                    )
                    for feed in feeds
                ]
            )
            return 0

        if args.command == "inbox":
            _refresh(store)
            articles = store.list_unread()
            if args.format == "json":
                print_inbox_json(articles)
            elif not articles:
                print_empty("No unread articles.")
            else:
                print_inbox_table(articles)
            return 0

        if args.command == "read":
            marked = store.mark_read(args.article_ids or None)
            if marked == 0:
                if args.article_ids:
                    print_empty("No matching unread articles.")
                else:
                    print_empty("No unread articles.")
                return 0
            print_success(f"Marked {marked} article(s) as read")
            return 0

        print_error(f"Unknown command: {args.command}")
        return 1


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        raise SystemExit(1)
    try:
        raise SystemExit(run(args))
    except BrokenPipeError:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
