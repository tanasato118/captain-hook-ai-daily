#!/usr/bin/env python3
"""
AI News Discord Bot v2 — マルチソース + Claude Haiku 翻訳

ソース:
  RSS  : TechCrunch AI / The Verge AI / VentureBeat AI
         MIT Tech Review / HuggingFace Blog / OpenAI News
  X API: 主要 AI 公式アカウント (news) / マネタイズ系 (monetize)

処理:
  Claude Haiku でフィルタリング → 日本語翻訳・要約 → Discord 送信

必要な環境変数（プロジェクトルートの .env に記載）:
  X_BEARER_TOKEN    — developer.x.com の Bearer Token
  DISCORD_WEBHOOK   — Discord Webhook URL
  ANTHROPIC_API_KEY — Anthropic API Key
"""
from __future__ import annotations

import os
import sys

# スクリプトと同階層を sys.path に追加（lib パッケージの import のため）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta, timezone

from lib.claude_client import filter_and_translate
from lib.discord_client import build_embed, send_embeds
from lib.sources import RSS_SOURCES, fetch_rss, fetch_x_posts

JST = timezone(timedelta(hours=9))


def load_dotenv_if_present() -> None:
    """カレントワーキングディレクトリ or スクリプト同階層の .env を読み込む。

    GitHub Actions 上では env 経由で値が渡るためこの関数は no-op になる。
    ローカル実行時は repo ルートの .env を参照する。
    """
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]
    env_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not env_path:
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and not os.environ.get(key, "").strip():
                os.environ[key] = val


def main() -> None:
    load_dotenv_if_present()

    bearer       = os.environ.get("X_BEARER_TOKEN",    "").strip()
    webhook      = os.environ.get("DISCORD_WEBHOOK",   "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    missing = [k for k, v in [
        ("X_BEARER_TOKEN",    bearer),
        ("DISCORD_WEBHOOK",   webhook),
        ("ANTHROPIC_API_KEY", anthropic_key),
    ] if not v]
    if missing:
        print(f"ERROR: 未設定の環境変数: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(JST)
    date_str = now.strftime("%Y年%m月%d日")

    embeds: list[dict] = [{
        "title": f"AI Daily — {date_str}",
        "description": (
            "**ソース**: TechCrunch / The Verge / VentureBeat / MIT Tech Review / HuggingFace / X\n"
            "**処理**: Claude Haiku にてフィルタリング・日本語翻訳・要約済み\n"
            "**Tips**: 48h以内・エンゲージメント順（いいね + RT×5 + 引用×3）"
        ),
        "color": 0x5865F2,
        "footer": {"text": "毎朝 9:00 JST 自動配信 | EA系 AI News Bot"},
    }]

    # ------------------------------------------------------------------
    # ニュース: RSS 3 ソース + X 公式アカウント
    # ------------------------------------------------------------------
    print("[news] RSS 取得中...")
    news_items = []
    for name, url in RSS_SOURCES["news"]:
        items = fetch_rss(name, url)
        print(f"  {name}: {len(items)} 件")
        news_items.extend(items)

    print("[news] X 取得中...")
    x_news = fetch_x_posts("news", bearer, max_results=10)
    print(f"  X/news: {len(x_news)} 件")
    news_items.extend(x_news)

    print(f"[news] Claude フィルタ中 (計 {len(news_items)} 件)...")
    curated_news = filter_and_translate(news_items, "news", anthropic_key, max_output=5)
    print(f"  -> {len(curated_news)} 件選出")
    embed = build_embed("news", curated_news)
    if embed:
        embeds.append(embed)

    # ------------------------------------------------------------------
    # 技術情報: RSS 3 ソース
    # ------------------------------------------------------------------
    print("[tech] RSS 取得中...")
    tech_items = []
    for name, url in RSS_SOURCES["tech"]:
        items = fetch_rss(name, url)
        print(f"  {name}: {len(items)} 件")
        tech_items.extend(items)

    print(f"[tech] Claude フィルタ中 (計 {len(tech_items)} 件)...")
    curated_tech = filter_and_translate(tech_items, "tech", anthropic_key, max_output=5)
    print(f"  -> {len(curated_tech)} 件選出")
    embed = build_embed("tech", curated_tech)
    if embed:
        embeds.append(embed)

    # ------------------------------------------------------------------
    # Tips: Claude/ChatGPT/Gemini 使い方（X API・48h・エンゲージ順）
    # ------------------------------------------------------------------
    print("[tips] X 取得中 (48h)...")
    tips_items = fetch_x_posts("tips", bearer, max_results=20, hours=48)
    print(f"  X/tips: {len(tips_items)} 件 (エンゲージ降順)")

    print(f"[tips] Claude フィルタ中 (計 {len(tips_items)} 件)...")
    curated_tips = filter_and_translate(tips_items, "tips", anthropic_key, max_output=5)
    print(f"  -> {len(curated_tips)} 件選出")
    embed = build_embed("tips", curated_tips)
    if embed:
        embeds.append(embed)

    # ------------------------------------------------------------------
    # マネタイズ（国内）: note RSS + X 日本語検索
    # ------------------------------------------------------------------
    print("[monetize_jp] note RSS 取得中...")
    jp_items = []
    for name, url in RSS_SOURCES["monetize_jp"]:
        items = fetch_rss(name, url)
        print(f"  {name}: {len(items)} 件")
        jp_items.extend(items)

    print("[monetize_jp] X 取得中 (日本語)...")
    x_jp = fetch_x_posts("monetize_jp", bearer, max_results=15, hours=48)
    print(f"  X/monetize_jp: {len(x_jp)} 件")
    jp_items.extend(x_jp)

    print(f"[monetize_jp] Claude フィルタ中 (計 {len(jp_items)} 件)...")
    curated_jp = filter_and_translate(jp_items, "monetize_jp", anthropic_key, max_output=5)
    print(f"  -> {len(curated_jp)} 件選出")
    embed = build_embed("monetize_jp", curated_jp)
    if embed:
        embeds.append(embed)

    # ------------------------------------------------------------------
    # マネタイズ（海外）: X 英語検索
    # ------------------------------------------------------------------
    print("[monetize] X 取得中 (海外)...")
    monetize_items = fetch_x_posts("monetize", bearer, max_results=15, hours=48)
    print(f"  X/monetize: {len(monetize_items)} 件")

    print(f"[monetize] Claude フィルタ中 (計 {len(monetize_items)} 件)...")
    curated_monetize = filter_and_translate(monetize_items, "monetize", anthropic_key, max_output=5)
    print(f"  -> {len(curated_monetize)} 件選出")
    embed = build_embed("monetize", curated_monetize)
    if embed:
        embeds.append(embed)

    # ------------------------------------------------------------------
    # Discord 送信
    # ------------------------------------------------------------------
    print(f"\nDiscord 送信中 ({len(embeds)} embeds)...")
    send_embeds(webhook, embeds)
    print(f"完了 @ {now.isoformat()}")


if __name__ == "__main__":
    main()
