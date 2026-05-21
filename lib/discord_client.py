"""
Discord Webhook にメッセージを送信するモジュール。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .claude_client import CuratedItem

_DISCORD_EMBED_TOTAL_CHAR_LIMIT = 6000
_DISCORD_MAX_SEND_ATTEMPTS = 3
_DISCORD_EMBED_TITLE_LIMIT = 256
_DISCORD_FIELD_NAME_LIMIT = 256
_DISCORD_FIELD_VALUE_LIMIT = 1024

_EMBED_META: dict[str, tuple[str, int]] = {
    # category -> (title, color)
    "news":        ("🌐 最新AIニュース",                              0xFF6B6B),
    "tech":        ("⚙️ AI技術情報",                                  0x6BCF7F),
    "tips":        ("💡 主要AIツール Tips（48h高エンゲージ）",          0x7289DA),
    "creative_ai": ("🎬 AI画像・AI動画",                               0x9B59B6),
    "company_updates": ("🏢 AI各社アップデート",                       0x3498DB),
    "monetize_jp": ("🇯🇵 AI副業マネタイズ（note・Brain・国内）",       0xE84393),
    "monetize":    ("🌍 AI副業マネタイズ（海外・全手法）",             0xFFE66D),
}


def _embed_char_count(embed: dict) -> int:
    """Discord's 6000 character limit is counted across all embeds in one message."""
    return (
        len(embed.get("title", ""))
        + len(embed.get("description", ""))
        + sum(
            len(field.get("name", "")) + len(field.get("value", ""))
            for field in embed.get("fields", [])
        )
        + len(embed.get("footer", {}).get("text", ""))
    )


def _chunk_embeds(embeds: list[dict]) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for embed in embeds:
        embed_chars = _embed_char_count(embed)
        if current and current_chars + embed_chars > _DISCORD_EMBED_TOTAL_CHAR_LIMIT:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(embed)
        current_chars += embed_chars

    if current:
        chunks.append(current)
    return chunks


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip() + "…"


def _field_value(item: CuratedItem) -> str:
    link = f"\n[→ 元記事 / 元ポスト]({item.url})  `{item.source}`"
    summary_limit = max(0, _DISCORD_FIELD_VALUE_LIMIT - len(link))
    return f"{_truncate(item.summary_ja, summary_limit)}{link}"


def build_embed(category: str, items: list[CuratedItem]) -> dict | None:
    """CuratedItem リストから Discord embed dict を構築する。空ならNone。"""
    if not items:
        return None

    title, color = _EMBED_META.get(category, (category, 0x5865F2))
    fields = [
        {
            "name":   _truncate(item.title_ja, _DISCORD_FIELD_NAME_LIMIT),
            "value":  _field_value(item),
            "inline": False,
        }
        for item in items
    ]
    return {
        "title": _truncate(title, _DISCORD_EMBED_TITLE_LIMIT),
        "color": color,
        "fields": fields,
    }


def send_embeds(webhook_url: str, embeds: list[dict]) -> None:
    """Discord Webhook に embeds を送信する（Discord の文字数制限に合わせて分割）。"""
    for chunk in _chunk_embeds(embeds):
        payload = json.dumps({"embeds": chunk}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent":   "DiscordBot (https://github.com/ea-bot, 1.0.0)",
            },
            method="POST",
        )
        for attempt in range(1, _DISCORD_MAX_SEND_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status not in (200, 204):
                        raise RuntimeError(f"Discord 応答 {resp.status}")
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                if e.code != 429 and e.code < 500:
                    raise RuntimeError(f"Discord HTTP {e.code}: {body[:300]}") from e
                if attempt == _DISCORD_MAX_SEND_ATTEMPTS:
                    raise RuntimeError(f"Discord HTTP {e.code}: {body[:300]}") from e
                retry_after = e.headers.get("Retry-After") if e.headers else None
                delay = float(retry_after) if retry_after else attempt * 2
                print(f"Discord retry {attempt}/{_DISCORD_MAX_SEND_ATTEMPTS}: HTTP {e.code}")
                time.sleep(delay)
