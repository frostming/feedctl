# feedctl

`feedctl` 是一个本地优先的 RSS/Atom 命令行工具。订阅、文章和已读状态都保存在 SQLite 中，不依赖远端服务。终端界面使用 Rich 提供颜色、表格和抓取进度展示；`inbox` 也支持适合 agent 消费的 JSON 输出。

## 安装

需要 Python 3.10 或更高版本：

```console
python -m pip install -e .
```

默认数据库位于 `$XDG_DATA_HOME/feedctl/feedctl.db`，未设置 `XDG_DATA_HOME` 时使用 `~/.local/share/feedctl/feedctl.db`。可通过 `FEEDCTL_DB` 或全局参数 `--database` 覆盖。

## 使用

```console
feedctl add https://example.com/feed.xml
feedctl remove https://example.com/feed.xml
feedctl import subscriptions.opml
feedctl export -o subscriptions.opml
feedctl list
feedctl inbox
feedctl inbox --format json
feedctl read
feedctl read 12 18 23
```

`add` 会先抓取并验证 RSS/Atom XML，从 feed 的 `title` 元素取得订阅名称，同时缓存响应中的文章。无法抓取、XML 非法或缺少标题时不会添加订阅。

不带 `-o` 的 `export` 会把 OPML 写到标准输出：

```console
feedctl export > subscriptions.opml
```

## 阅读语义

`inbox` 会并发刷新全部源，并在交互式终端的 stderr 显示抓取进度；重定向或管道环境会自动关闭动态进度。抓取使用 ETag 和 Last-Modified 条件请求，完成后按发布时间从新到旧输出。默认使用 Rich 表格：

```console
feedctl inbox
```

默认表格显示发布日期、来源、标题和链接，不显示内部文章 ID。日期统一按 UTC 展示；源没有提供发布日期时显示 `—`。

需要稳定的 agent/脚本输入时使用 JSON 格式；该模式的 stdout 始终是合法 JSON，包括没有未读文章的情况：

```console
feedctl inbox --format json
```

```json
{
  "count": 1,
  "articles": [
    {
      "id": 12,
      "source": "Example Feed",
      "title": "Article title",
      "url": "https://example.com/article",
      "published_at": "2026-08-12T10:00:00+00:00"
    }
  ]
}
```

`inbox` 不会改变已读状态，可以重复执行。单个源刷新失败时只告警，不影响其他源或已经缓存的文章。

`read` 用于标记已读：

```console
# Mark selected articles
feedctl read 12 18 23

# Mark every unread article
feedctl read
```

删除订阅也会删除该订阅的本地文章。

## 开发与验证

```console
pdm sync
pdm test
```
