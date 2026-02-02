# ECHO OS Barebone - アーキテクチャ設計書

> このドキュメントは、ECHO OS Bareboneを受け取った開発者が、システムの思想・設計・拡張方法を完全に理解するためのマスタードキュメントです。

---

## 目次

1. [設計思想と哲学](#1-設計思想と哲学)
2. [5層RAGアーキテクチャ](#2-5層ragアーキテクチャ)
3. [ディレクトリ構成と各ファイルの役割](#3-ディレクトリ構成と各ファイルの役割)
4. [マルチテナント設計](#4-マルチテナント設計)
5. [LLM抽象化レイヤー](#5-llm抽象化レイヤー)
6. [拡張ポイントとカスタマイズ方法](#6-拡張ポイントとカスタマイズ方法)
7. [新しい業種への適用手順](#7-新しい業種への適用手順)
8. [環境変数リファレンス](#8-環境変数リファレンス)
9. [デプロイメントパターン](#9-デプロイメントパターン)
10. [データ収集ツール（クローラー）](#10-データ収集ツールクローラー)
11. [メンテナンス方針](#11-メンテナンス方針)

---

## 1. 設計思想と哲学

### 1.1 なぜこのOSを作ったのか

ECHO OS Bareboneは、**業種固有の専門知識を持つAIアシスタント**を迅速に構築するための基盤OSです。

従来のアプローチでは、新しい業種向けAIを作るたびにゼロから開発していました。しかし、実際には以下の要素は業種を問わず共通です：

- マルチテナント認証・認可
- 会話履歴の管理
- LLMとの通信と抽象化
- 検索（RAG）パイプライン
- 管理画面とAPI

**このOSは「共通部分」を提供し、「業種固有部分」だけを追加すれば動くように設計されています。**

### 1.2 設計原則

#### 原則1: 環境変数による設定

ハードコードされた値はゼロ。すべての設定は環境変数で制御します。

```python
# 悪い例（ハードコード）
SERVICE_NAME = "社労士ヘルパーくん"

# 良い例（環境変数）
SERVICE_NAME = os.getenv("SERVICE_NAME", "AIアシスタント")
```

#### 原則2: レイヤーの独立性

各レイヤー（L1〜L5）は独立してON/OFF可能。使わないレイヤーは無効化できます。

```bash
L1_ENABLED=true   # 業界共通知識
L3_ENABLED=false  # 事務所知識（使わない場合）
L4_ENABLED=true   # クライアント固有データ
L5_ENABLED=true   # 会話履歴
```

#### 原則3: プレースホルダーによる拡張性

各レイヤーの検索ロジックは「プレースホルダー」として用意されています。実装者は自分の業種に合わせて中身を埋めるだけです。

```python
def _get_l1_context(query: str) -> str:
    """Get L1 (industry knowledge) context.

    Note: Implement with your L1 search service.
    """
    # ← ここに業種固有の検索ロジックを実装
    return ""
```

#### 原則4: フォールバックの連鎖

LLMプロバイダーは自動フォールバック。Claude → OpenAI → Gemini の順で試行します。

```
Claude (推奨) → 失敗 → OpenAI (フォールバック) → 失敗 → Gemini (最終手段)
```

#### 原則5: 観測可能性（Observability）

すべてのリクエストにtrace_idを付与。どのレイヤーを通過したか追跡可能です。

```json
{
  "trace_id": "abc123",
  "route_trace": ["gateway", "query_handler", "L1", "L4", "llm"],
  "layers_accessed": ["L1", "L4", "L5"]
}
```

### 1.3 このOSで作れるもの

- 社労士向けAIアシスタント（労働法、就業規則）
- 税理士向けAIアシスタント（税法、判例検索）
- 弁護士向けAIアシスタント（判例、法令検索）
- 医師向けAIアシスタント（診療ガイドライン、薬剤情報）
- カスタマーサポートAI（FAQ、過去チケット検索）

---

## 2. 5層RAGアーキテクチャ

### 2.1 レイヤー概要

```
┌─────────────────────────────────────────────────────────────────┐
│                        ユーザークエリ                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Intent Classifier                          │
│         (クエリの意図を分類し、優先レイヤーを決定)                │
└─────────────────────────────────────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
    ┌──────────┐          ┌──────────┐          ┌──────────┐
    │    L1    │          │    L4    │          │    L5    │
    │ 業界共通  │          │クライアント│         │ 会話履歴  │
    │  知識    │          │ 固有データ │         │          │
    └──────────┘          └──────────┘          └──────────┘
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         LLM (Claude)                            │
│              コンテキストを統合し、回答を生成                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          レスポンス                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 各レイヤーの詳細

#### L1: 業界共通知識層

**目的**: 業界全体で共通の知識（法令、規則、ガイドライン）を提供

**データソース例**:
- 法令（e-Gov法令API）
- 業界ガイドライン
- 公的機関の通達
- 教科書的な解説

**バックエンド選択肢**:
- Azure AI Search（推奨、セマンティック検索対応）
- FAISS（ローカル、コスト重視）

**環境変数**:
```bash
L1_ENABLED=true
L1_USE_AZURE_AI_SEARCH=true
AZURE_SEARCH_L1_INDEX_NAME=your-l1-index
```

#### L2: 事務所知識層（将来拡張）

**目的**: 事務所固有のナレッジ（マニュアル、テンプレート）

**現状**: プレースホルダーとして設計のみ存在

#### L3: クライアント共有知識層

**目的**: 複数クライアントで共有できる知識

**データソース例**:
- 事務所が作成したFAQ
- 業界ニュース
- 共通テンプレート

**バックエンド選択肢**:
- S3 + ローカルインデックス
- OneDrive/Google Drive連携

#### L4: クライアント固有データ層

**目的**: 特定クライアントのみに関連するデータ

**データソース例**:
- 就業規則（そのクライアント専用）
- 契約書
- 過去の相談履歴

**バックエンド選択肢**:
- Azure AI Search（マルチテナント対応）
- DynamoDB + ベクトルインデックス

**環境変数**:
```bash
L4_ENABLED=true
L4_USE_AZURE_AI_SEARCH=true
```

#### L5: 会話履歴層

**目的**: 過去の会話を記憶し、文脈を維持

**機能**:
- 直近N件の会話取得
- セマンティック検索による関連会話取得
- セッション間での記憶維持

**バックエンド選択肢**:
- DynamoDB（スケーラブル）
- SQLite（ローカル開発用）

**環境変数**:
```bash
L5_ENABLED=true
L5_K_RECENT=5
L5_SEMANTIC_ENABLED=false
```

### 2.3 Intent Classifier（意図分類器）

クエリの意図を分類し、どのレイヤーを優先するか決定します。

**分類カテゴリ**:

| カテゴリ | 説明 | 優先レイヤー |
|---------|------|-------------|
| `EXTERNAL_LEGAL` | 業界一般の知識を問う | L1優先 |
| `INTERNAL_REGULATION` | 自社/クライアント固有 | L4優先 |
| `PROFESSIONAL_ADVICE` | 専門家の判断を求める | L1+L3+L4 |
| `CONTEXT_FOLLOWUP` | 直前の会話への追加質問 | L5優先 |

**分類方法**:
1. **キーワードマッチ**（高速、1ms）: 明確なパターンがある場合
2. **LLM分類**（高精度、500ms）: 曖昧なクエリの場合

---

## 3. ディレクトリ構成と各ファイルの役割

```
echo-os-barebone/
├── src/                          # メインソースコード
│   ├── api/                      # FastAPI アプリケーション
│   │   ├── main.py              # ★ エントリーポイント、ルーティング定義
│   │   ├── query_handler.py     # ★ クエリ処理、RAGパイプライン実行
│   │   ├── deps.py              # 依存性注入（テナントコンテキスト取得）
│   │   ├── auth_api.py          # 認証API（JWT発行/検証）
│   │   ├── security_middleware.py # セキュリティヘッダー、レート制限
│   │   ├── middleware/
│   │   │   └── host_resolver.py # ★ ホストベースのテナント解決
│   │   └── llm/                 # LLM抽象化レイヤー
│   │       ├── base.py          # 抽象基底クラス
│   │       ├── factory.py       # ★ プロバイダー選択とフォールバック
│   │       ├── claude_provider.py
│   │       ├── openai_provider.py
│   │       ├── gemini_provider.py
│   │       ├── types.py         # LLMMessage, LLMResponse型定義
│   │       └── prompts/
│   │           ├── __init__.py
│   │           └── system.py    # ★★ 業種固有プロンプト（要カスタマイズ）
│   │
│   ├── services/                 # ビジネスロジック
│   │   ├── intent_classifier_service.py  # ★ 意図分類（要カスタマイズ）
│   │   ├── tenant_service.py    # テナント管理
│   │   ├── client_service.py    # クライアント管理
│   │   ├── jwt_service.py       # JWT操作
│   │   └── legacy_resolver.py   # 旧形式ID変換（後方互換）
│   │
│   ├── models/                   # データモデル
│   │   ├── tenant.py            # TenantContext
│   │   └── user.py              # User
│   │
│   ├── core/                     # 共通基盤
│   │   └── logging.py           # 構造化ロギング、トレース
│   │
│   └── utils/
│       └── env.py               # ★★ 全環境変数の一元管理
│
├── scripts/                      # バッチ処理スクリプト
│   └── common/
│       ├── chunker.py           # テキストチャンキング
│       ├── embedder.py          # 埋め込みベクトル生成
│       └── build_index.py       # インデックス構築
│
├── frontend/                     # フロントエンド
│   └── index.html               # 最小テンプレート（要カスタマイズ）
│
├── data/                         # データディレクトリ（空）
│   └── .gitkeep
│
├── docs/                         # ドキュメント
│   └── ARCHITECTURE.md          # このファイル
│
├── .env.example                  # 環境変数テンプレート
├── requirements.txt              # Python依存関係
├── Dockerfile                    # Dockerイメージ定義
├── docker-compose.yml            # ローカル開発用
└── README.md                     # クイックスタート
```

### ★マーク付きファイルの説明

| ファイル | 重要度 | 説明 |
|---------|--------|------|
| `main.py` | ★ | FastAPIアプリ本体。ミドルウェア設定、エンドポイント定義 |
| `query_handler.py` | ★ | RAGパイプラインの実行。各レイヤーからコンテキスト取得 |
| `host_resolver.py` | ★ | `client.example.com` → テナント特定 |
| `factory.py` | ★ | LLMプロバイダー選択とフォールバック処理 |
| `system.py` | ★★ | **必ずカスタマイズ**。業種固有のシステムプロンプト |
| `intent_classifier_service.py` | ★ | **カスタマイズ推奨**。業種固有のキーワードパターン |
| `env.py` | ★★ | 全環境変数の定義。新しい設定はここに追加 |

---

## 4. マルチテナント設計

### 4.1 テナント解決フロー

```
リクエスト: https://client-a.example.com/chat
                    │
                    ▼
        ┌───────────────────────┐
        │   HostResolverMiddleware   │
        │   Host: client-a.example.com │
        │   → tenant_slug: client-a    │
        └───────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │   TenantService           │
        │   slug → tenant_id        │
        │   → tenant_id: t_12345    │
        └───────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │   TenantContext           │
        │   - tenant_id: t_12345    │
        │   - client_id: c_67890    │
        │   - source: host          │
        └───────────────────────┘
```

### 4.2 テナント識別方法

1. **ホストベース**（推奨）: `client-a.example.com` → `client-a`
2. **ヘッダーベース**: `X-Tenant-ID: 12345`
3. **JWTベース**: トークン内の`tenant_id`クレーム

### 4.3 データ分離

各レイヤーでテナント/クライアントIDによりデータを分離：

```python
# L4検索の例
results = azure_search.search(
    query=query,
    filter=f"tenant_id eq '{tenant_id}' and client_id eq '{client_id}'"
)
```

---

## 5. LLM抽象化レイヤー

### 5.1 設計思想

LLMプロバイダーに依存しないコードを書けるよう、抽象化レイヤーを提供。

```python
# プロバイダーを意識しないコード
from src.api.llm import llm_factory, LLMMessage

messages = [
    LLMMessage(role="system", content="あなたは専門家です"),
    LLMMessage(role="user", content="質問があります")
]
response = llm_factory.generate(messages)
print(response.content)  # プロバイダーに関係なく同じ形式
```

### 5.2 フォールバック機構

```python
# factory.py での優先順位設定
PROVIDER_PRIORITY = ["claude", "openai", "gemini"]

# 自動フォールバック
# Claude失敗 → OpenAI試行 → Gemini試行
response = llm_factory.generate(messages)
print(response.provider)       # 実際に使用したプロバイダー
print(response.fallback_used)  # フォールバックしたかどうか
```

### 5.3 プロバイダー追加方法

新しいLLMプロバイダーを追加する場合：

1. `src/api/llm/` に新しいプロバイダークラスを作成
2. `LLMProvider` 基底クラスを継承
3. `factory.py` にプロバイダーを登録

```python
# 例: mistral_provider.py
class MistralProvider(LLMProvider):
    def generate(self, messages, config):
        # Mistral API呼び出し
        ...
```

---

## 6. 拡張ポイントとカスタマイズ方法

### 6.1 必須カスタマイズ（これだけは必ずやる）

#### 1. システムプロンプト（`src/api/llm/prompts/system.py`）

業種に合わせたペルソナと回答スタイルを定義：

```python
from ...utils.env import env

SYSTEM_PROMPT = f"""
あなたは{env.PERSONA_NAME}です。
{env.OFFICE_NAME}の専門家として、クライアントからの質問に回答します。

## あなたの専門分野
- 税法（所得税、法人税、消費税）
- 税務判例
- 確定申告手続き

## 回答スタイル
- 法的根拠を明示する
- 条文番号を引用する
- 実務的なアドバイスを含める

## 参照コンテキスト
### 法令・通達（L1）
{l1_context}

### クライアント固有情報（L4）
{l4_context}
"""
```

#### 2. 環境変数（`.env`）

```bash
# サービスアイデンティティ
SERVICE_NAME=税務アシスタント
PERSONA_NAME=税務エキスパート
BASE_DOMAIN=your-domain.com

# APIキー
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx  # フォールバック用

# レイヤー設定
L1_ENABLED=true
L4_ENABLED=true
L5_ENABLED=true
```

### 6.2 推奨カスタマイズ

#### 意図分類パターン（`intent_classifier_service.py`）

業種固有のキーワードパターンを追加：

```python
# 税理士版の例
EXTERNAL_LEGAL_PATTERNS = [
    r"(所得税|法人税|消費税|相続税)",
    r"(確定申告|年末調整|源泉徴収)",
    r"(国税庁|税務署)",
    r"第?\d+条",  # 条文参照
]

INTERNAL_REGULATION_PATTERNS = [
    r"(当社|弊社|うちの会社)",
    r"(決算|経理|会計)",
]
```

#### L1検索ロジック（`query_handler.py`）

プレースホルダーを実装：

```python
def _get_l1_context(query: str) -> str:
    """税法・通達を検索"""
    from ..services.l1_search_service import search_tax_law

    results = search_tax_law(query, top_k=5)

    if not results:
        return ""

    context_parts = []
    for r in results:
        context_parts.append(f"【{r['source']}】\n{r['content']}")

    return "\n\n".join(context_parts)
```

### 6.3 オプションカスタマイズ

- フロントエンドUI（`frontend/index.html`）
- 管理画面（`frontend/admin.html`）
- バッチ処理スクリプト（`scripts/`）

---

## 7. 新しい業種への適用手順

### ステップ1: リポジトリをコピー

```bash
cp -r echo-os-barebone your-industry-app
cd your-industry-app
git init
```

### ステップ2: 環境変数を設定

```bash
cp .env.example .env
# .envを編集
```

```bash
SERVICE_NAME=税務アシスタント
PERSONA_NAME=税務エキスパート
BASE_DOMAIN=tax-helper.example.com
```

### ステップ3: システムプロンプトを作成

`src/api/llm/prompts/system.py` を業種に合わせて編集。

### ステップ4: 意図分類パターンを調整

`src/services/intent_classifier_service.py` のパターンを業種に合わせて編集。

### ステップ5: L1データを準備

業界共通知識をAzure AI SearchまたはFAISSに投入：

```bash
# インデックス構築スクリプトを作成
python scripts/build_l1_index.py
```

### ステップ6: ローカルで動作確認

```bash
docker-compose up
curl http://localhost:8000/health
```

### ステップ7: デプロイ

GitHub Actions、AWS App Runner、などお好みの方法で。

---

## 8. 環境変数リファレンス

### サービスアイデンティティ

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `SERVICE_NAME` | サービス表示名 | `AIアシスタント` |
| `OFFICE_NAME` | 事務所名（オプション） | `""` |
| `PERSONA_NAME` | AIペルソナ名 | `AIエキスパート` |
| `BASE_DOMAIN` | ベースドメイン | `example.com` |
| `DEFAULT_OFFICE_ID` | デフォルトオフィスID | `default` |

### レイヤー設定

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `L1_ENABLED` | L1層有効化 | `true` |
| `L3_ENABLED` | L3層有効化 | `false` |
| `L4_ENABLED` | L4層有効化 | `true` |
| `L5_ENABLED` | L5層有効化 | `false` |

### LLM設定

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `ANTHROPIC_API_KEY` | Claude APIキー | `""` |
| `OPENAI_API_KEY` | OpenAI APIキー | `""` |
| `GOOGLE_API_KEY` | Gemini APIキー | `""` |

### Azure AI Search

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `AZURE_SEARCH_ENDPOINT` | エンドポイント | `""` |
| `AZURE_SEARCH_API_KEY` | APIキー | `""` |
| `AZURE_SEARCH_L1_INDEX_NAME` | L1インデックス名 | `l1-legal-hybrid` |
| `L1_USE_AZURE_AI_SEARCH` | Azure使用フラグ | `false` |

### AWS/DynamoDB

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `AWS_REGION` | AWSリージョン | `ap-northeast-1` |
| `DDB_TABLE_CONV` | 会話テーブル | `ConversationMemory` |
| `DDB_TABLE_TENANTS` | テナントテーブル | `Tenants` |

全環境変数は `src/utils/env.py` で定義されています。

---

## 9. デプロイメントパターン

### パターン1: AWS App Runner（推奨）

```yaml
# GitHub Actions workflow
- name: Build & Push to ECR
- name: Update App Runner Service
- name: Smoke Test
```

### パターン2: Docker Compose（開発/小規模）

```bash
docker-compose up -d
```

### パターン3: Kubernetes（大規模）

Helm chartを作成して展開。

---

## 10. データ収集ツール（クローラー）

このOSには、L1データを収集するためのクローラーが同梱されています。

### 10.1 同梱クローラー

| ファイル | 説明 | 用途例 |
|---------|------|--------|
| `scripts/common/crawler_web.py` | 汎用Webクローラー | セキュリティサイト、ドキュメント、ニュースサイト |
| `scripts/common/crawler_egov.py` | e-Gov法令APIクローラー | 日本の法令（労働法、税法等） |

### 10.2 汎用Webクローラーの使い方

**セキュリティ関連サイトをクロールする例**:

```python
from scripts.common.crawler_web import WebCrawler, CrawlConfig

# 設定
config = CrawlConfig(
    seed_urls=[
        "https://www.cisa.gov/news-events/cybersecurity-advisories",
        "https://nvd.nist.gov/vuln/search",
    ],
    allowed_path_prefixes=["/news-events/", "/vuln/"],
    max_urls=200,           # 最大200ページ
    max_depth=2,            # リンクを2階層まで追跡
    request_delay=2.0,      # 2秒間隔（サーバー負荷軽減）
    user_agent="YourCompany-SecurityBot/1.0",
)

# クロール実行
crawler = WebCrawler()
results = crawler.crawl(config)

# 結果確認
for r in results:
    if r.success:
        print(f"取得: {r.url} ({len(r.text)} chars)")

# チャンク形式に変換（インデックス構築用）
from scripts.common.crawler_web import convert_to_chunks
chunks = convert_to_chunks(results)
```

**特徴**:
- BFS（幅優先探索）でリンクを追跡
- HTMLとPDFに対応
- エンコーディング自動検出
- レート制限（`request_delay`）
- ドメイン/パス制限

### 10.3 e-Gov法令クローラーの使い方

**日本の法令をクロールする例**:

```python
from scripts.common.crawler_egov import EgovApiCrawler, convert_to_chunks

# クローラー初期化
crawler = EgovApiCrawler()

# 法令IDを指定してクロール
# 法令IDは https://elaws.e-gov.go.jp/ で確認可能
law_ids = [
    "322AC0000000049",  # 労働基準法
    "349AC0000000116",  # 雇用保険法
    "418AC0000000004",  # 石綿健康被害救済法
]

results = crawler.fetch_all_laws(law_ids)

# 結果確認
for r in results:
    if r.success:
        print(f"{r.law_name}: {len(r.articles)} articles")

# チャンク形式に変換
chunks = convert_to_chunks(results)
```

**法令IDの調べ方**:
1. https://elaws.e-gov.go.jp/ にアクセス
2. 法令を検索して詳細ページを開く
3. URLの `lawid=` パラメータが法令ID

### 10.4 クロール→インデックス構築の流れ

```python
# 1. クロール
from scripts.common.crawler_web import WebCrawler, CrawlConfig, convert_to_chunks
from scripts.common.chunker import SemanticChunker
from scripts.common.build_index import build_azure_index

config = CrawlConfig(
    seed_urls=["https://example.com/docs"],
    max_urls=100,
)
crawler = WebCrawler()
results = crawler.crawl(config)

# 2. チャンキング
chunks = convert_to_chunks(results)

# 3. セマンティックチャンキング（オプション）
semantic_chunker = SemanticChunker(max_tokens=500)
refined_chunks = []
for chunk in chunks:
    refined_chunks.extend(
        semantic_chunker.chunk(chunk["content"], chunk["source"])
    )

# 4. インデックス構築
build_azure_index(
    chunks=refined_chunks,
    index_name="my-security-index",
    recreate=True
)
```

### 10.5 クローラー拡張

新しいデータソース用のクローラーを追加する場合：

1. `scripts/common/` に新しいクローラーファイルを作成
2. `CrawlResult` 互換の結果を返す
3. `convert_to_chunks()` 関数を実装

```python
# 例: scripts/common/crawler_rss.py
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class RssResult:
    url: str
    title: str
    content: str
    published: str
    success: bool = True

class RssCrawler:
    def fetch_feed(self, feed_url: str) -> List[RssResult]:
        # RSS/Atomフィードをパース
        ...

def convert_to_chunks(results: List[RssResult]) -> List[Dict]:
    return [
        {
            "content": r.content,
            "source": r.url,
            "metadata": {"title": r.title, "published": r.published}
        }
        for r in results if r.success
    ]
```

---

## 付録: よくある質問

### Q: 新しいレイヤー（L6など）を追加できる？

A: はい。`query_handler.py` に新しいレイヤー取得関数を追加し、`env.py` にフラグを追加するだけです。

### Q: 複数LLMを同時に使える？

A: 現在は順次フォールバック。並列呼び出しは未実装ですが、`factory.py` を拡張すれば可能です。

### Q: オンプレミスで動かせる？

A: はい。Azure/AWSへの依存はオプション。FAISS + SQLiteで完全ローカル動作可能です。

---

## 11. メンテナンス方針

### 11.1 このOSの出自

ECHO OS Bareboneは、**社労士版プラットフォーム（sharoushi）** から汎用OS部分を抽出して作成されました。

```
sharoushi（社労士版）
    ↓ 汎用部分を抽出
echo-os-barebone（汎用OS）
    ↓ コピーしてカスタマイズ
tains-demo（税理士版）、その他業種版...
```

### 11.2 OS進化の反映方法

sharoushiで開発中に「これはOS機能だ」と気づいた場合：

**Claude Codeに依頼する**:
```
「この変更、echo-os-bareboneにも反映して」
```

Claude Codeが：
1. 変更内容を確認
2. 業種固有部分（社労士固有のハードコード等）を除去
3. echo-os-bareboneに適用
4. commit & push

### 11.3 業種固有 vs OS機能の判断基準

| 分類 | 例 | barebone反映 |
|------|-----|-------------|
| **OS機能** | LLMフォールバック改善、認証強化、新ミドルウェア | ✅ 反映する |
| **業種固有** | 社労士試験対応、労働法キーワード、36協定パターン | ❌ 反映しない |
| **グレーゾーン** | 新しいクローラー、特定API連携 | 汎用化して反映 |

### 11.4 ライセンシーへの提供

このリポジトリをそのままライセンシーに提供可能。
ライセンシーは `docs/ARCHITECTURE.md` を読んで全機能を理解し、カスタマイズを開始できる。

---

## 改訂履歴

| 日付 | バージョン | 変更内容 |
|------|-----------|---------|
| 2025-02-02 | 1.0.0 | 初版作成 |
| 2025-02-02 | 1.1.0 | メンテナンス方針追加 |

---

> **このドキュメントに関する質問・提案は、リポジトリのIssueに記載してください。**
