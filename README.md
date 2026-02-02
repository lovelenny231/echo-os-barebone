# ECHO OS Barebone

汎用マルチテナントRAG/LLMプラットフォーム（業種非依存）

## このOSについて

ECHO OS Bareboneは、**業種固有の専門知識を持つAIアシスタント**を迅速に構築するための基盤OSです。

- 社労士向け → 労働法、就業規則
- 税理士向け → 税法、判例検索
- 弁護士向け → 判例、法令検索
- その他どんな業種にも適用可能

**共通部分（認証、RAG、LLM連携）はすべて用意済み。業種固有のプロンプトとデータを追加するだけで動きます。**

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** | **必読** - 設計思想、5層RAGアーキテクチャ、カスタマイズ方法 |
| [.env.example](.env.example) | 環境変数テンプレート |

## クイックスタート

### 1. このリポジトリをコピー

```bash
cp -r echo-os-barebone your-industry-app
cd your-industry-app
```

### 2. 環境変数を設定

```bash
cp .env.example .env
# .env を編集
```

最低限必要な設定:
```bash
SERVICE_NAME=税務アシスタント
PERSONA_NAME=税務エキスパート
ANTHROPIC_API_KEY=sk-ant-xxx
```

### 3. 起動

```bash
# Docker
docker-compose up

# または直接
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 4. 動作確認

```bash
curl http://localhost:8000/health
```

## 必須カスタマイズ

1. **システムプロンプト**: `src/api/llm/prompts/system.py`
2. **環境変数**: `.env`

詳細は [ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照。

## ディレクトリ構成

```
echo-os-barebone/
├── src/
│   ├── api/                 # FastAPI アプリケーション
│   │   ├── main.py          # エントリーポイント
│   │   ├── query_handler.py # RAGパイプライン
│   │   ├── llm/             # LLM抽象化レイヤー
│   │   │   └── prompts/     # ★ プロンプト（要カスタマイズ）
│   │   └── middleware/      # テナント解決、セキュリティ
│   ├── services/            # ビジネスロジック
│   │   └── intent_classifier_service.py  # ★ 意図分類（カスタマイズ推奨）
│   ├── models/              # データモデル
│   ├── core/                # ロギング等
│   └── utils/
│       └── env.py           # ★ 環境変数定義
├── scripts/
│   └── common/              # チャンキング、埋め込み、インデックス構築
├── frontend/                # UIテンプレート
├── data/                    # データ（空）
├── docs/
│   └── ARCHITECTURE.md      # ★ 設計ドキュメント
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 5層RAGアーキテクチャ

```
L1: 業界共通知識     (Azure AI Search / FAISS)
L2: 事務所知識       (将来拡張)
L3: クライアント共有  (S3 / OneDrive)
L4: クライアント固有  (Azure AI Search / DynamoDB)
L5: 会話履歴        (DynamoDB / SQLite)
```

各レイヤーは `L1_ENABLED=true/false` で個別にON/OFF可能。

## API エンドポイント

| エンドポイント | メソッド | 説明 |
|---------------|---------|------|
| `/health` | GET | ヘルスチェック |
| `/chat` | POST | チャット処理 |
| `/chat/office` | POST | 事務所向けチャット |
| `/admin` | GET | 管理画面 |
| `/rag/status` | GET | RAGステータス |

## ライセンス

Private - All Rights Reserved

---

**詳細なアーキテクチャ、設計思想、カスタマイズ方法は [ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照してください。**
