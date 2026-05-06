"""
AI ニュースソースから記事・ポストを取得するモジュール。
対応: RSS フィード / X API v2
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    excerpt: str       # 本文抜粋（最大 600 文字）
    source: str
    engagement: int = 0  # X のエンゲージメントスコア（RSS は 0）


_CUTOFF_HOURS_RSS = 25   # RSS は 25 時間以内
_X_API_HOST = "https://api.x.com"

_NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
}

# ---------------------------------------------------------------------------
# RSS ソース定義
# ---------------------------------------------------------------------------

RSS_SOURCES: dict[str, list[tuple[str, str]]] = {
    "news": [
        ("TechCrunch AI",  "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge AI",   "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("VentureBeat",    "https://venturebeat.com/feed/"),
    ],
    "tech": [
        ("MIT Tech Review",  "https://www.technologyreview.com/feed/"),
        ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml"),
        ("OpenAI News",      "https://openai.com/news/rss.xml"),
    ],
    # note.com のハッシュタグ RSS（AIマネタイズ関連）
    "monetize_jp": [
        ("note/AI",            "https://note.com/hashtag/AI/rss"),
        ("note/ChatGPT",       "https://note.com/hashtag/ChatGPT/rss"),
        ("note/AIマネタイズ",  "https://note.com/hashtag/AI%E3%83%9E%E3%83%8D%E3%82%BF%E3%82%A4%E3%82%BA/rss"),
        ("note/AI副業",        "https://note.com/hashtag/AI%E5%89%AF%E6%A5%AD/rss"),
        ("note/収益化",        "https://note.com/hashtag/%E5%8F%8E%E7%9B%8A%E5%8C%96/rss"),
    ],
}

# ---------------------------------------------------------------------------
# X API クエリ定義
# ---------------------------------------------------------------------------

X_QUERIES: dict[str, str] = {
    # 日本語：note・国内プラットフォームでの AI マネタイズ
    "monetize_jp": (
        "(note OR Brain OR Tips OR Coconala OR ランサーズ OR クラウドワークス"
        " OR Udemy OR ストアカ OR zenn OR アフィリエイト OR ブログ)"
        " (AI OR ChatGPT OR Claude OR Gemini OR Midjourney OR 生成AI)"
        " (販売 OR 収益化 OR マネタイズ OR 売れた OR 副業 OR 稼いだ OR 月収 OR 収入 OR 売上)"
        " -is:retweet -is:reply lang:ja"
    ),
    "news": (
        "(from:OpenAI OR from:AnthropicAI OR from:GoogleDeepMind"
        " OR from:Meta OR from:mistralai OR from:xai OR from:nvidia)"
        " -is:retweet -is:reply"
    ),
    "tips": (
        # Claude / ChatGPT / Gemini の最新技術・使い方に特化
        "(Claude OR ChatGPT OR \"GPT-4o\" OR \"GPT-4\" OR Gemini OR \"Claude 3\" OR \"Claude 4\")"
        " (tip OR trick OR prompt OR workflow OR tutorial OR \"how to\""
        " OR update OR feature OR released OR \"new feature\" OR \"just dropped\")"
        " -is:retweet -is:reply lang:en"
    ),
    "monetize": (
        "(AI OR ChatGPT OR Midjourney OR Claude OR Gemini OR GPT OR \"Stable Diffusion\""
        " OR \"AI art\" OR \"AI writing\" OR \"AI video\" OR \"AI automation\")"
        " (freelance OR \"side hustle\" OR \"passive income\" OR solopreneur OR indie"
        ' OR "make money" OR earning OR sold OR income OR "$" OR revenue'
        " OR client OR fiverr OR upwork OR etsy OR gumroad OR sellling OR selling"
        " OR course OR ebook OR template OR prompt OR automation OR workflow)"
        " -is:retweet -is:reply lang:en"
    ),
}

# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """HTML タグと余分な空白を除去する。"""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except Exception:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None


def _find_text(elem: ET.Element, tags: list[str]) -> str:
    for tag in tags:
        found = elem.find(tag, _NS)
        if found is not None and found.text:
            return found.text
    return ""


def _calc_engagement(metrics: dict) -> int:
    """エンゲージメントスコアを計算する（インプレッションの代理指標）。"""
    return (
        metrics.get("like_count", 0)
        + metrics.get("retweet_count", 0) * 5
        + metrics.get("quote_count", 0) * 3
        + metrics.get("reply_count", 0)
        + metrics.get("bookmark_count", 0) * 2
    )


# ---------------------------------------------------------------------------
# RSS 取得
# ---------------------------------------------------------------------------

def fetch_rss(source_name: str, url: str) -> list[Item]:
    """RSS/Atom フィードを取得して Item リストを返す（25 時間以内のみ）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_CUTOFF_HOURS_RSS)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-news-bot/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
    except (urllib.error.URLError, OSError) as e:
        print(f"  RSS fetch failed [{source_name}]: {e}")
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"  RSS parse failed [{source_name}]: {e}")
        return []

    items_xml = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry"
    )

    results: list[Item] = []
    for item in items_xml:
        title = _strip_html(
            _find_text(item, ["title", "{http://www.w3.org/2005/Atom}title"])
        )
        link_text = item.findtext("link", "")
        if not link_text:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            link_text = atom_link.get("href", "") if atom_link is not None else ""

        desc_raw = _find_text(
            item,
            [
                "description",
                "content:encoded",
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            ],
        )
        excerpt = _strip_html(desc_raw)[:600]

        pub = _parse_date(
            _find_text(item, [
                "pubDate", "dc:date",
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
            ])
        )
        if pub and pub.tzinfo and pub < cutoff:
            continue
        if not title or not link_text:
            continue

        results.append(Item(
            title=title,
            url=link_text.strip(),
            excerpt=excerpt,
            source=source_name,
        ))

    return results


# ---------------------------------------------------------------------------
# X API 取得
# ---------------------------------------------------------------------------

def fetch_x_posts(
    category: str,
    bearer: str,
    max_results: int = 20,
    hours: int = 48,
) -> list[Item]:
    """
    X API v2 recent search で Item リストを返す。
    エンゲージメントスコア降順でソートして返す。
    hours: 何時間以内の投稿を対象にするか（デフォルト 48h）
    """
    query = X_QUERIES.get(category, "")
    if not query:
        return []

    start_time = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = urllib.parse.urlencode({
        "query":        query,
        "max_results":  max_results,
        "tweet.fields": "author_id,public_metrics,text",
        "expansions":   "author_id",
        "user.fields":  "username",
        "start_time":   start_time,
    })
    req = urllib.request.Request(
        f"{_X_API_HOST}/2/tweets/search/recent?{params}",
        headers={
            "Authorization": f"Bearer {bearer}",
            "User-Agent":    "ai-news-bot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  X API error [{category}]: HTTP {e.code} - {body[:200]}")
        return []
    except urllib.error.URLError as e:
        print(f"  X API network error [{category}]: {e.reason}")
        return []

    users: dict[str, str] = {
        u["id"]: u["username"]
        for u in data.get("includes", {}).get("users", [])
    }

    # エンゲージメントスコアで降順ソート
    tweets = sorted(
        data.get("data", []),
        key=lambda t: _calc_engagement(t.get("public_metrics", {})),
        reverse=True,
    )

    results: list[Item] = []
    for tweet in tweets:
        username = users.get(tweet.get("author_id", ""), "unknown")
        m = tweet.get("public_metrics", {})
        likes = m.get("like_count", 0)
        rts   = m.get("retweet_count", 0)
        score = _calc_engagement(m)
        results.append(Item(
            title=f"@{username}  L:{likes} RT:{rts}",
            url=f"https://x.com/{username}/status/{tweet['id']}",
            excerpt=tweet["text"][:600],
            source=f"X/{category}",
            engagement=score,
        ))
    return results
