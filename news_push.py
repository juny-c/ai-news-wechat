#!/usr/bin/env python3
import html
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FEEDS_FILE = ROOT / "config" / "feeds.txt"
DEFAULT_LIMIT = 10


@dataclass
class NewsItem:
    title: str
    link: str
    summary: str
    source: str
    published: datetime


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_list(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ai-news-wechat/0.1 (+https://github.com/example/ai-news-wechat)"
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def text_of(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return clean_text(child.text)
    return ""


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def parse_feed(url: str, body: bytes) -> list[NewsItem]:
    root = ET.fromstring(body)
    channel = root.find("channel")
    source = text_of(channel, ("title",)) if channel is not None else ""
    items = []

    if channel is not None:
        nodes = channel.findall("item")
        for node in nodes:
            title = text_of(node, ("title",))
            link = text_of(node, ("link",))
            summary = text_of(node, ("description", "{http://purl.org/rss/1.0/modules/content/}encoded"))
            published = parse_date(text_of(node, ("pubDate", "{http://purl.org/dc/elements/1.1/}date")))
            if title and link:
                items.append(NewsItem(title, link, summary, source or domain_name(url), published))
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    source = text_of(root, ("{http://www.w3.org/2005/Atom}title",)) or domain_name(url)
    for node in root.findall("atom:entry", ns):
        title = text_of(node, ("{http://www.w3.org/2005/Atom}title",))
        link = ""
        for link_node in node.findall("atom:link", ns):
            href = link_node.attrib.get("href", "")
            rel = link_node.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                link = href
                break
        summary = text_of(node, ("{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"))
        published = parse_date(text_of(node, ("{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated")))
        if title and link:
            items.append(NewsItem(title, link, summary, source, published))
    return items


def domain_name(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc
    return host.removeprefix("www.")


def load_feeds() -> list[str]:
    if not FEEDS_FILE.exists():
        return []
    feeds = []
    for raw_line in FEEDS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            feeds.append(line)
    return feeds


def score_item(item: NewsItem, keywords: list[str]) -> int:
    keyword_score = sum(1 for keyword in keywords if keyword_matches(keyword, item))
    age_hours = max(0, (datetime.now(timezone.utc) - item.published).total_seconds() / 3600)
    recency_score = max(0, 168 - int(age_hours))
    source_bonus = 30 if "ai" in item.source.lower() else 0
    return keyword_score * 1000 + source_bonus + recency_score


def is_relevant(item: NewsItem, keywords: list[str]) -> bool:
    if item.published < recent_cutoff():
        return False
    return any(keyword_matches(keyword, item) for keyword in keywords)


def keyword_matches(keyword: str, item: NewsItem) -> bool:
    haystack = f"{item.title} {item.summary[:360]} {item.source}".lower()
    if not keyword:
        return False
    if keyword.isascii() and keyword.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", haystack) is not None
    return keyword in haystack


def recent_cutoff() -> datetime:
    days = int(os.getenv("NEWS_RECENT_DAYS", "7"))
    return datetime.fromtimestamp(time.time() - days * 86400, tz=timezone.utc)


def collect_news() -> list[NewsItem]:
    keywords = env_list("NEWS_KEYWORDS", "ai,openai,anthropic,deepmind,llm,agent,人工智能,大模型")
    items: list[NewsItem] = []
    for feed in load_feeds():
        try:
            items.extend(parse_feed(feed, fetch_url(feed)))
        except (ET.ParseError, urllib.error.URLError, TimeoutError) as exc:
            print(f"warn: failed to fetch {feed}: {exc}", file=sys.stderr)
    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in sorted(items, key=lambda x: score_item(x, keywords), reverse=True):
        if not is_relevant(item, keywords):
            continue
        key = canonical_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def canonical_key(item: NewsItem) -> str:
    parsed = urllib.parse.urlparse(item.link)
    path = parsed.path.rstrip("/")
    if parsed.netloc and path:
        return f"{parsed.netloc}{path}".lower()
    return re.sub(r"\W+", "", item.title.lower())


def summarize(text: str, width: int = 130) -> str:
    if not text:
        return "暂无摘要，可点击原文查看详情。"
    return textwrap.shorten(text, width=width, placeholder="...")


def render_markdown(items: list[NewsItem]) -> str:
    limit = int(os.getenv("NEWS_LIMIT", str(DEFAULT_LIMIT)))
    selected = items[:limit]
    today = datetime.now().strftime("%Y-%m-%d")
    if not selected:
        return f"# AI 新闻简报 {today}\n\n今天没有抓到可用新闻，请检查 RSS 源或网络。"

    lines = [f"# AI 新闻简报 {today}", ""]
    for index, item in enumerate(selected, 1):
        date = item.published.astimezone().strftime("%Y-%m-%d")
        lines.extend(
            [
                f"## {index}. {item.title}",
                f"- 来源：{item.source}",
                f"- 发布日期：{date}",
                f"- 摘要：{summarize(item.summary)}",
                f"- 原文：{item.link}",
                "",
            ]
        )

    lines.append("## 今日最值得关注")
    for item in selected[:3]:
        lines.append(f"- {item.title}")
    return "\n".join(lines).strip()


def post_json(url: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def post_form(url: str, payload: dict) -> str:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def push_message(title: str, content: str) -> None:
    provider = os.getenv("PUSH_PROVIDER", "stdout").lower()
    if provider == "stdout":
        print(content)
        return

    if provider == "pushplus":
        token = require_env("PUSHPLUS_TOKEN")
        response = post_json(
            "https://www.pushplus.plus/send",
            {"token": token, "title": title, "content": content, "template": "markdown"},
        )
    elif provider == "wxpusher":
        app_token = require_env("WXPUSHER_APP_TOKEN")
        uids = [uid.strip() for uid in require_env("WXPUSHER_UIDS").split(",") if uid.strip()]
        response = post_json(
            "https://wxpusher.zjiecode.com/api/send/message",
            {
                "appToken": app_token,
                "content": content,
                "summary": title[:20],
                "contentType": 3,
                "uids": uids,
            },
        )
    elif provider == "serverchan":
        sendkey = require_env("SERVERCHAN_SENDKEY")
        response = post_form(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            {"title": title, "desp": content},
        )
    else:
        raise SystemExit(f"Unknown PUSH_PROVIDER: {provider}")

    print(response)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    load_dotenv(ROOT / ".env")
    title = f"AI 新闻简报 {time.strftime('%Y-%m-%d')}"
    content = render_markdown(collect_news())
    push_message(title, content)


if __name__ == "__main__":
    main()
