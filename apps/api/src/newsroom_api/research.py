from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx


RSS_SOURCES: tuple[tuple[str, str, float], ...] = (
    ("Anthropic", "https://www.anthropic.com/rss.xml", 1.3),
    ("OpenAI", "https://openai.com/news/rss.xml", 1.3),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml", 1.3),
    (
        "TechCrunch AI",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        1.0,
    ),
    (
        "The Verge AI",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        1.0,
    ),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", 1.0),
)

HN_TOP_STORIES_URL = (
    "https://hacker-news.firebaseio.com/v0/topstories.json"
)
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _clean_text(value: str | None, limit: int = 600) -> str:
    cleaned = html.unescape(_TAG_RE.sub(" ", value or ""))
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:limit]


def _stable_story_id(url: str, title: str) -> str:
    digest = hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()[:20]
    return f"story-{digest}"


def _parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element:
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names and child.text:
            return child.text.strip()
    return ""


def _entry_url(element: ET.Element) -> str:
    for child in element:
        if child.tag.rsplit("}", 1)[-1].lower() != "link":
            continue
        href = child.attrib.get("href", "").strip()
        relation = child.attrib.get("rel", "alternate")
        if href and relation in {"", "alternate"}:
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def _topic_for(title: str) -> str:
    lowered = title.lower()
    topic_terms = (
        ("research", ("paper", "research", "benchmark", "study")),
        ("models", ("model", "llm", "reasoning", "agent")),
        ("developer-tools", ("api", "developer", "coding", "sdk")),
        ("products", ("launch", "release", "product", "feature")),
        ("business", ("funding", "acquire", "revenue", "company")),
        ("policy", ("law", "regulation", "policy", "government")),
    )
    for topic, terms in topic_terms:
        if any(term in lowered for term in terms):
            return topic
    return "general"


def _is_recent(published: dt.datetime, now: dt.datetime) -> bool:
    age = now - published
    return dt.timedelta(0) <= age <= dt.timedelta(hours=24)


def _rss_items(
    xml_text: str,
    *,
    source: str,
    source_weight: float,
    now: dt.datetime,
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    elements = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
    ]
    stories: list[dict[str, Any]] = []
    for element in elements[:20]:
        title = _clean_text(_child_text(element, ("title",)), 220)
        url = _entry_url(element)
        published_value = _child_text(
            element, ("pubdate", "published", "updated", "date")
        )
        published = _parse_datetime(published_value)
        if not title or not url or published is None:
            continue
        if not _is_recent(published, now):
            continue
        summary = _clean_text(
            _child_text(
                element,
                ("description", "summary", "content", "encoded"),
            ),
            600,
        )
        if not summary:
            summary = "Open the linked source for its verified report."
        recency = max(
            0.05,
            1 - ((now - published).total_seconds() / (24 * 60 * 60)),
        )
        rank_score = source_weight * recency
        stories.append(
            {
                "id": _stable_story_id(url, title),
                "title": title,
                "source": source,
                "url": url,
                "published_at": published.isoformat().replace("+00:00", "Z"),
                "summary": summary,
                "why_it_matters": (
                    "Review the linked source and set a human editorial angle "
                    "before drafting."
                ),
                "score": round(rank_score, 4),
                "selected": False,
                "topic": _topic_for(title),
                "is_demo": False,
            }
        )
    return stories


async def _fetch_rss_source(
    client: httpx.AsyncClient,
    source: str,
    url: str,
    weight: float,
    now: dt.datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return (
            _rss_items(
                response.text,
                source=source,
                source_weight=weight,
                now=now,
            ),
            None,
        )
    except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
        return [], f"{source}: {type(exc).__name__}"


async def _fetch_hacker_news(
    client: httpx.AsyncClient, now: dt.datetime
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        response = await client.get(HN_TOP_STORIES_URL)
        response.raise_for_status()
        ids = response.json()
        if not isinstance(ids, list):
            raise ValueError("unexpected top stories response")
        responses = await asyncio.gather(
            *(
                client.get(HN_ITEM_URL.format(item_id=item_id))
                for item_id in ids[:30]
            ),
            return_exceptions=True,
        )
        stories: list[dict[str, Any]] = []
        for item_response in responses:
            if isinstance(item_response, Exception):
                continue
            try:
                item_response.raise_for_status()
                item = item_response.json()
            except (httpx.HTTPError, ValueError):
                continue
            if not isinstance(item, dict):
                continue
            score = int(item.get("score") or 0)
            timestamp = item.get("time")
            title = _clean_text(item.get("title"), 220)
            url = str(item.get("url") or "").strip()
            if score <= 100 or not timestamp or not title:
                continue
            if not url:
                url = f"https://news.ycombinator.com/item?id={item.get('id')}"
            published = dt.datetime.fromtimestamp(
                int(timestamp), tz=dt.timezone.utc
            )
            if not _is_recent(published, now):
                continue
            recency = max(
                0.05,
                1 - ((now - published).total_seconds() / (24 * 60 * 60)),
            )
            engagement = min(3.0, score / 100)
            stories.append(
                {
                    "id": _stable_story_id(url, title),
                    "title": title,
                    "source": "Hacker News",
                    "url": url,
                    "published_at": published.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "summary": (
                        "Hacker News discussion item. Open the linked source "
                        "for the verified report."
                    ),
                    "why_it_matters": (
                        "Its engagement passed the configured research "
                        "threshold. A human editor must decide its relevance."
                    ),
                    "score": round(recency * engagement, 4),
                    "selected": False,
                    "topic": _topic_for(title),
                    "is_demo": False,
                }
            )
        return stories, None
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return [], f"Hacker News: {type(exc).__name__}"


def _deduplicate(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    unique: list[dict[str, Any]] = []
    for story in sorted(
        stories, key=lambda item: float(item["score"]), reverse=True
    ):
        parsed = urlparse(story["url"])
        normalized_url = (
            f"{parsed.netloc.lower()}{parsed.path.rstrip('/').lower()}"
        )
        normalized_title = re.sub(
            r"[^a-z0-9]+", " ", story["title"].lower()
        ).strip()
        title_is_duplicate = any(
            SequenceMatcher(
                None,
                normalized_title,
                previous_title,
                autojunk=False,
            ).ratio()
            >= 0.88
            for previous_title in seen_titles
        )
        if normalized_url in seen_urls or title_is_duplicate:
            continue
        seen_urls.add(normalized_url)
        seen_titles.append(normalized_title)
        unique.append(story)
    return unique


async def fetch_live_shortlist(
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], list[str], int]:
    now = _utc_now()
    headers = {
        "User-Agent": (
            "GianiNewsroom/0.1 (+local human-in-the-loop research assistant)"
        )
    }
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers=headers,
    ) as client:
        rss_tasks = [
            _fetch_rss_source(client, source, url, weight, now)
            for source, url, weight in RSS_SOURCES
        ]
        results = await asyncio.gather(
            *rss_tasks, _fetch_hacker_news(client, now)
        )

    all_stories: list[dict[str, Any]] = []
    errors: list[str] = []
    for stories, error in results:
        all_stories.extend(stories)
        if error:
            errors.append(error)
    fetched = len(all_stories)
    return _deduplicate(all_stories)[:8], errors, fetched
