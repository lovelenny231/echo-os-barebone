# ECHO OS Barebone

汎用マルチテナントRAG/LLMプラットフォーム（業種非依存）

## 概要

ECHO OS Bareboneは、マルチテナント対応のRAGチャットシステムを構築するための基盤OSです。
業種固有のプロンプトやデータを追加することで、様々な専門分野向けAIアシスタントを構築できます。

## アーキテクチャ

### レイヤー構成

```
L1: 業界共通知識     (Azure AI Search / FAISS対応)
L2: 事務所知識       (S3 / ローカル対応) [将来拡張]
L3: クライアント固有  (OneDrive / GDrive対応) [将来拡張]
L4: 外部データ       (Azure AI Search / DynamoDB対応)
L5: 会話履歴        (DynamoDB / SQLite対応)
```

各レイヤーは環境変数で ON/OFF 可能です。

### ディレクトリ構成

```
echo-os-barebone/
├── src/
│   ├── api/
│   │   ├── main.py           # FastAPI基盤
│   │   ├── deps.py           # 依存性注入
│   │   ├── auth_api.py       # 認証API
│   │   ├── admin_api.py      # 管理API
│   │   ├── client_api.py     # クライアントAPI
│   │   └── query_handler.py  # クエリ処理
│   ├── middleware/
│   │   ├── host_resolver.py  # テナント解決
│   │   └── security.py       # セキュリティ
│   ├── services/
│   │   ├── l1_rag_service.py            # L1検索
│   │   ├── l4_processing_pipeline.py    # L4処理
│   │   ├── azure_search_service.py      # Azure AI Search
│   │   ├── intent_classifier_service.py # 意図分類
│   │   └── memory_service.py            # L5メモリ
│   ├── llm/
│   │   ├── base.py           # LLM抽象化
│   │   ├── factory.py        # LLMファクトリ
│   │   ├── claude_provider.py
│   │   ├── openai_provider.py
│   │   └── prompts/
│   │       └── system.py     # プロンプトテンプレート（空）
│   └── models/
│       ├── tenant.py         # テナントモデル
│       └── client.py         # クライアントモデル
├── backend/
│   ├── auth_manager.py       # 認証マネージャー
│   ├── layer5_memory_system.py  # L5メモリ
│   └── dynamodb_layer5_system.py
├── scripts/
│   └── common/
│       ├── chunker.py        # チャンキング
│       ├── embedder.py       # 埋め込み
│       └── build_index.py    # インデックス構築
├── frontend/
│   └── index.html            # 最小テンプレート
├── data/                     # データ（空）
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 環境変数

### 必須設定

```bash
# サービス設定
SERVICE_NAME=AIアシスタント
OFFICE_NAME=事務所名
PERSONA_NAME=AIエキスパート
BASE_DOMAIN=example.com

# デフォルトテナント
DEFAULT_OFFICE_ID=default
```

### レイヤー設定

```bash
# レイヤー有効化
L1_ENABLED=true
L3_ENABLED=false
L4_ENABLED=true
L5_ENABLED=true

# バックエンド選択
L1_USE_AZURE_AI_SEARCH=true
L4_USE_AZURE_AI_SEARCH=true
```

### LLM設定

```bash
# Anthropic Claude (推奨)
ANTHROPIC_API_KEY=sk-ant-xxx

# OpenAI (フォールバック)
OPENAI_API_KEY=sk-xxx

# Google Gemini (オプション)
GOOGLE_API_KEY=xxx
```

### Azure AI Search設定

```bash
AZURE_SEARCH_ENDPOINT=https://xxx.search.windows.net
AZURE_SEARCH_API_KEY=xxx
AZURE_SEARCH_INDEX_NAME=your-index
AZURE_SEARCH_L1_INDEX_NAME=your-l1-index
```

### AWS設定

```bash
AWS_REGION=ap-northeast-1
DDB_TABLE_CONV=ConversationMemory
DDB_TABLE_TENANTS=Tenants
DDB_TABLE_CLIENTS=Clients
```

## クイックスタート

### 1. 環境変数の設定

```bash
cp .env.example .env
# .envを編集して必要な値を設定
```

### 2. ローカル起動

```bash
# Dockerを使用
docker-compose up

# または直接起動
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 3. ヘルスチェック

```bash
curl http://localhost:8000/health
```

## カスタマイズ方法

### 1. プロンプトの設定

`src/api/llm/prompts/system.py` を編集して、業種固有のシステムプロンプトを設定します。

```python
SYSTEM_PROMPT = """
あなたは{PERSONA_NAME}です。
{company_name}の担当者からの質問に答えます。
...
"""
```

### 2. 意図分類のカスタマイズ

`src/services/intent_classifier_service.py` のキーワードパターンを業種に合わせて調整します。

### 3. L1データの投入

Azure AI Searchインデックスに業界共通知識を投入します。
`scripts/common/build_index.py` を参考にしてください。

## API エンドポイント

| エンドポイント | メソッド | 説明 |
|---------------|---------|------|
| `/health` | GET | ヘルスチェック |
| `/chat` | POST | チャット処理 |
| `/chat/office` | POST | 事務所向けチャット |
| `/admin` | GET | 管理画面 |
| `/tenants` | GET | テナント一覧 |
| `/admin/l1/status` | GET | L1インデックス状態 |

## ライセンス

Private - All Rights Reserved

## 作成元

このOSは社労士版プラットフォームから汎用部分を抽出して作成されました。
