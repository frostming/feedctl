---
name: feedctl
description: Manage local RSS and Atom subscriptions and article read state with the feedctl CLI. Use when an agent needs to add or remove feeds, import or export OPML, inspect subscriptions, fetch unread articles, or mark selected or all articles as read.
---

# Operate feedctl

Use `feedctl` as the only interface to subscription and read-state data. Do not edit the SQLite database directly unless the user explicitly requests database repair or debugging.

## Preserve state safely

- Use `feedctl inbox --format json` to fetch and inspect unread articles. This command does not mark articles as read.
- Never use `feedctl read` merely to view articles.
- Prefer `feedctl read ARTICLE_ID...` with IDs from the latest inbox response.
- Run bare `feedctl read` only when the user explicitly asks to mark every unread article as read. There is no unread or replay command to reverse this action.
- Run `feedctl remove URL` only when the user explicitly requests removal. Removing a feed also deletes its locally stored articles.
- Keep stdout and stderr separate when consuming JSON. Fetch progress and warnings are written to stderr.

## Select the database

Use the configured default database unless the user supplies another location. The resolution order is:

1. Global `--database PATH`
2. `FEEDCTL_DB`
3. `$XDG_DATA_HOME/feedctl/feedctl.db`
4. `~/.local/share/feedctl/feedctl.db`

Place `--database` before the subcommand:

```console
feedctl --database /path/to/feedctl.db inbox --format json
```

Use the same database for every command in one workflow.

## Inspect unread articles

Always request JSON for agent workflows:

```console
feedctl inbox --format json
```

Parse stdout as this schema:

```json
{
  "count": 2,
  "articles": [
    {
      "id": 42,
      "source": "Example Feed",
      "title": "Example article",
      "url": "https://example.com/article",
      "published_at": "2026-08-12T10:00:00+00:00"
    }
  ]
}
```

Treat `articles` as ordered from newest to oldest. `published_at` is a UTC ISO 8601 timestamp or `null` when the source provides no publication date. Treat `id` as a stable local identifier for subsequent `read` commands. An empty inbox is still valid JSON:

```json
{"count": 0, "articles": []}
```

The command refreshes feeds concurrently before returning cached unread articles. A failed source produces a warning on stderr but does not prevent other sources or cached articles from being returned. Do not reject a valid JSON result solely because stderr contains warnings.

Use the default table only when preparing human-readable terminal output. It shows the publication date, source, title, and link; it intentionally omits internal article IDs:

```console
feedctl inbox
```

## Mark articles as read

Mark one or more selected articles with IDs from the latest inbox result:

```console
feedctl read 42 57 61
```

Mark all unread articles only after explicit user intent:

```console
feedctl read
```

The operation is transactional. Duplicate, unknown, and already-read IDs are ignored. If exact verification matters, run `feedctl inbox --format json` again and check that the selected IDs are absent.

## Manage subscriptions

Add and validate one feed:

```console
feedctl add https://example.com/feed.xml
```

`add` fetches and parses the RSS or Atom XML before writing. It requires a feed title, stores that title and conditional-request metadata, and caches the initial articles. A fetch, parse, or missing-title failure leaves no subscription.

Remove one feed by its exact URL:

```console
feedctl remove https://example.com/feed.xml
```

List subscriptions for human inspection:

```console
feedctl list
```

For structured inspection of all subscription URLs, export OPML instead of parsing the Rich table:

```console
feedctl export
```

## Import and export OPML

Import nested OPML outlines. Existing URLs are ignored, so repeating the import is safe:

```console
feedctl import subscriptions.opml
```

Import does not fetch every feed immediately. Run `feedctl inbox --format json` afterward when current articles and refreshed feed metadata are required.

Export raw OPML to stdout:

```console
feedctl export > subscriptions.opml
```

Or let feedctl write the file:

```console
feedctl export --output subscriptions.opml
```

Do not mix status text with stdout when using raw OPML or JSON output.

## Handle failures

- Treat exit code `0` as command completion, but still inspect structured output and stderr warnings.
- Treat exit code `1` from `add` as an existing feed and from `remove` as a missing feed.
- Treat exit code `2` from `add` as a fetch or feed-validation failure and from `import` as invalid or unreadable OPML.
- Do not retry permanent parse or validation failures without changing the input.
- Retry transient network failures conservatively; do not add duplicate subscriptions during retries.
