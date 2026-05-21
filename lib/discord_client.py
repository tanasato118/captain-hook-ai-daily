"""
Discord Webhook にメッセージを送信するモジュール。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .claude_client import CuratedItem

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


def build_embed(category: str, items: list[CuratedItem]) -> dict | None:
    """CuratedItem リストから Discord embed dict を構築する。空ならNone。"""
    if not items:
        return None

    title, color = _EMBED_META.get(category, (category, 0x5865F2))
    fields = [
        {
            "name":   item.title_ja,
            "value":  f"{item.summary_ja}\n[→ 元記事 / 元ポスト]({item.url})  `{item.source}`",
            "inline": False,
        }
        for item in items
    ]
    return {"title": title, "color": color, "fields": fields}


def send_embeds(webhook_url: str, embeds: list[dict]) -> None:
    """Discord Webhook に embeds を送信する（10 件ずつ分割）。"""
    for i in range(0, len(embeds), 10):
        payload = json.dumps({"embeds": embeds[i : i + 10]}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent":   "DiscordBot (https://github.com/ea-bot, 1.0.0)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(f"Discord 応答 {resp.status}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Discord HTTP {e.code}: {body[:300]}") from e
