"""
Claude API (Haiku) を使って記事リストをフィルタリング・翻訳・要約するモジュール。
バッチ処理でAPI呼び出し回数を最小化する。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .sources import Item

_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL   = "claude-haiku-4-5-20251001"

# カテゴリ別「有益」基準（プロンプトに埋め込む）
_CRITERIA: dict[str, str] = {
    "news": """\
・新モデル・製品のリリース（仕様・ベンチマーク・数値付き）
・OpenAI / Anthropic / Google / Meta 等主要企業の重要発表
・AI 規制・政策の変化（EU AI Act 等）
・OSS モデルリリース（Llama / Mistral 等）
・重要な資金調達・買収
除外: 意見記事・予測・重複カバレッジ""",

    "tech": """\
・新アーキテクチャ・学習手法（実装レベルで語れるもの）
・ベンチマーク比較（MMLU / HumanEval / MATH 等）
・推論最適化（量子化・投機的デコード・ファインチューニング等）
・新 API 機能・コンテキスト長拡張等の実用的な変化
・実用インパクトが高い研究論文
除外: マーケティング寄りの技術記事・数値なしの定性的な話""",

    "monetize_jp": """\
対象: 日本国内プラットフォームで個人が AI を活用してマネタイズする情報全般

【プラットフォーム別（すべて対象）】
・note: AI を使って記事・有料マガジン・メンバーシップを販売
・Brain / Tips: AI で情報商材・ノウハウ記事を作成・販売
・Coconala / ランサーズ / クラウドワークス: AI 代行サービスの出品・受注
・Udemy / ストアカ: AI ツールの使い方講座・プロンプト講座を作成・販売
・YouTube / TikTok / Instagram: AI コンテンツで収益化（広告・案件）
・ブログ / アフィリエイト: AI で記事量産してアフィリエイト収益
・Zenn: AI 技術記事を販売・Zenn Books

【有益の条件】
  ✅ 具体的な収益額・販売数・手順が書かれている
  ✅ 使用した AI ツール名が明記されている
  ✅ 再現可能な方法論・テンプレートが含まれる
  ✅ 新しいプラットフォーム活用の発見

【除外】
  × 企業・法人のサービス紹介
  × 具体性のない「AI で稼げる」系まとめ
  × 投資・FX・暗号資産
  × 採用・求人情報

  ※日本語の記事はそのまま日本語で要約してください。英語記事は翻訳。""",

    "tips": """\
対象: Claude / ChatGPT / Gemini / Perplexity / Copilot / NotebookLM / Cursor / Windsurf など主要AIツールの最新機能・実践的な使い方のみ
・新機能・新モデルのリリース情報（ChatGPT, Claude, Gemini, Perplexity, Copilot, NotebookLM, Cursor 等）
・エンゲージメントが高い（いいね・RT 多数）実践的なプロンプト・ワークフロー
・「こう使ったら驚くほど便利だった」系の具体的 Tips（手順が書いてあるもの）
・新しいコンテキスト長・マルチモーダル・エージェント・開発支援機能などの活用法
・48時間以内の投稿、エンゲージメント順に並んでいるので上位を優先
除外:
  × 抽象的な感想・雑談・ミーム
  × 比較意見だけで手法がないもの
  × 古い情報の再共有""",

    "creative_ai": """\
対象: AI画像・AI動画・生成メディア分野の新機能、使い方、実践ワークフロー
・Midjourney / Runway / Sora / Kling / Pika / Luma / Stable Diffusion / ComfyUI / Flux / DALL-E / Adobe Firefly 等の新モデル・新機能
・生成品質、制御性、動画尺、音声、編集、商用利用、API などの具体的な改善
・画像生成・動画生成のプロンプト、制作手順、ComfyUI ワークフロー、実例付き Tips
・広告素材、SNS動画、商品画像、サムネイルなど制作現場で使える活用法
有益の条件:
  ✅ ツール名・機能名・手順・設定値・比較結果のいずれかが具体的
  ✅ 実際の制作フローに転用できる
  ✅ 新しいモデルや機能の変化が分かる
除外:
  × 完成作品の自慢だけで手順がない投稿
  × 汎用的な「AI動画がすごい」系の感想
  × 権利・商用利用に関する根拠のない断言
  × 投資・トークン・暗号資産""",

    "company_updates": """\
対象: OpenAI / Anthropic / Google DeepMind / Meta AI / xAI / Mistral / NVIDIA / Microsoft / Perplexity などAI各社の公式・準公式アップデート
・新モデル、API、SDK、料金、提供地域、提供プラン、ベータ公開、一般公開
・プロダクト新機能、研究発表、ベンチマーク、OSS リリース、開発者向け更新
・企業戦略として重要な提携、買収、インフラ、GPU、エージェント関連発表
有益の条件:
  ✅ どの会社が何を出したかが具体的
  ✅ モデル名・API名・価格・提供範囲・性能指標などの確認可能な情報がある
  ✅ 開発・業務利用・情報収集に影響する
除外:
  × 公式根拠のない噂・リーク
  × 株価・投資目線だけの話
  × 比較煽り・感想だけ
  × 既存発表の単なる再掲""",

    "monetize": """\
対象: 個人・フリーランサーが副業として AI を活用してマネタイズできるあらゆる手法
現実的に稼げる手法であれば分野は問わない。以下はすべて対象:

【コンテンツ・クリエイティブ系】
・AI 画像生成（Midjourney / DALL-E / Stable Diffusion）でアート販売・Etsy・印刷物
・AI 動画生成（Sora / Runway / Kling）でショート動画・広告素材・YouTube
・AI 音声・音楽生成（Suno / ElevenLabs）でポッドキャスト・BGM・ナレーション販売
・AI でブログ・記事・メルマガ・SNS 投稿を量産してアフィリエイト・広告収益
・AI でデジタル商品（電子書籍・テンプレート・プロンプト集）を作成・販売

【フリーランス・サービス系】
・Fiverr / Upwork / クラウドワークスで AI 代行サービス（文章・翻訳・画像・動画）
・AI チャットボット・自動化ワークフローを中小企業向けに構築して販売
・AI コンサル・プロンプトエンジニアリングサービス
・AI を使ったコーディング代行・ノーコードアプリ開発

【プロダクト・SaaS 系】
・個人が AI を活用してミニ SaaS / ツールを作って販売（月額・買い切り）
・プロンプトマーケットプレイス（PromptBase 等）での販売
・AI で作ったコース・チュートリアルの販売（Udemy / Gumroad 等）

【自動化・エージェント系】
・n8n / Zapier + AI で業務自動化を受注・販売
・AI エージェントを使ったリサーチ・データ収集代行

有益の条件（以下のいずれかを満たすもの）:
  ✅ 具体的なツール名・手順・収益額が書かれている
  ✅ 再現可能な事例（「やってみたら月 X ドル稼げた」等）
  ✅ 新しいプラットフォーム・手法の発見

除外（重要）:
  × 企業・スタートアップの B2B 導入事例
  × 具体性ゼロの「AIで稼ぐ方法」系まとめ
  × 投資・株式・暗号資産トレード
  × 採用・人事・雇用側の話題""",
}

_CAT_NAME: dict[str, str] = {
    "news":        "最新AIニュース",
    "tech":        "AI技術情報",
    "tips":        "主要AIツールの使い方Tips",
    "creative_ai": "AI画像・AI動画",
    "company_updates": "AI各社アップデート",
    "monetize":    "AI副業マネタイズ（海外・個人向け）",
    "monetize_jp": "AI副業マネタイズ（国内／note・Brain等）",
}


@dataclass(frozen=True)
class CuratedItem:
    title_ja:   str
    summary_ja: str
    url:        str
    source:     str


def filter_and_translate(
    items: list[Item],
    category: str,
    api_key: str,
    max_output: int = 5,
) -> list[CuratedItem]:
    """
    Claude Haiku に記事リストを渡し、有益なものだけを日本語翻訳・要約して返す。
    入力が空なら空リストを返す。
    """
    if not items:
        return []

    cat_name = _CAT_NAME.get(category, category)
    criteria = _CRITERIA.get(category, "新しく、具体的で、実用的な情報")

    # トークン節約のため抜粋は 300 文字まで
    items_payload = [
        {"index": i, "title": item.title, "excerpt": item.excerpt[:300]}
        for i, item in enumerate(items)
    ]

    prompt = f"""あなたはAIニュースキュレーターです。以下の記事リストを評価し、有益なものだけを日本語に翻訳・要約してください。

カテゴリ: {cat_name}

【有益の基準】
{criteria}

【記事リスト】
{json.dumps(items_payload, ensure_ascii=False, indent=2)}

【回答ルール】
1. 有益と判断した記事のみ含める（最大 {max_output} 件）
2. 英語の内容は必ず日本語に翻訳する
3. summary_ja は 3 文以内、モデル名・数値・ツール名などの具体情報を含める
4. JSON 配列のみ出力する（コードブロック不要）

【出力形式】
[
  {{
    "index": <元リストのindex番号>,
    "title_ja": "日本語タイトル（簡潔に30文字以内）",
    "summary_ja": "3文以内の日本語要約。具体的な数値・名称を含める。"
  }}
]"""

    payload = json.dumps({
        "model":      _MODEL,
        "max_tokens": 2048,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        _API_URL,
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"  Claude API error [{category}]: HTTP {e.code} — {err[:300]}")
        return []
    except urllib.error.URLError as e:
        print(f"  Claude API network error [{category}]: {e.reason}")
        return []

    raw = body["content"][0]["text"].strip()

    # ```json ... ``` でラップされていても対応
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            stripped = part.removeprefix("json").strip()
            if stripped.startswith("["):
                raw = stripped
                break

    try:
        parsed: list[dict] = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  Claude response parse failed [{category}]: {e} — {raw[:200]}")
        return []

    results: list[CuratedItem] = []
    for entry in parsed:
        idx = entry.get("index", -1)
        if 0 <= idx < len(items):
            results.append(CuratedItem(
                title_ja=entry.get("title_ja", items[idx].title),
                summary_ja=entry.get("summary_ja", ""),
                url=items[idx].url,
                source=items[idx].source,
            ))
    return results
