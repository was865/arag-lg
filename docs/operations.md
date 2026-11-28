# 運用の手順

日々の起動・GPU 機・入庫と評価・止まったときの戻し方。決まりごと（何を守るか）は `AGENTS.md`、設計は `specs/`。

## 1. 開発機（Mac）で全体を起動する

```bash
cp .env.example .env   # 初回だけ。推論の構成 [A] オフライン / [B] 軽量 / [C] 混在 は .env.example の先頭を参照
make up                # compose で全体（postgres・qdrant・redis・api・worker・runner・web・mailpit）。開発構成
make up-prod           # 本番と同じ構成（build した image。compose.override.yaml を読まない）
```

| URL | 中身 |
|---|---|
| http://localhost:3100 | 画面（compose の `web`）。実際の質問はここで |
| http://localhost:8100 | API（`/healthz`・`/readyz`。readyz は推論の部品まで確かめる） |
| http://localhost:8025 | mailpit（確認・再設定のメール） |
| http://localhost:3100/dev/ui | UI 部品の見本（開発構成のときだけ） |

- `.env` の値は画面・ログ・コミットに出さない。テスト用アカウントも `.env` にある。
- 開発構成（`make up`）ではソースを容器に載せているので、保存すれば反映する（`web` は next dev、`api` は --reload、`runner`・`worker` は watchfiles で再起動）。作り直しは依存（`pyproject.toml`・`package.json`）を変えたときだけ `make up`。
- 本番の構成（`make up-prod`）では image で動くので、変えたら作り直す: `docker compose -f compose.yaml up -d --build --no-deps runner web`。開発構成に戻すときは `make up`。

### 外から使う（Tailscale）

- `.env` に `ARAG_EXTRA_ORIGINS=https://<機名>.<tailnet>.ts.net,http://<Tailscale の IP>:3100` を書き、`docker compose up -d web` で作り直す。localhost:3100 もそのまま使える。
- HTTPS の名前で開くには Mac で `tailscale serve --bg 3100`（初回は tailnet の管理画面で Serve と HTTPS 証明書を有効にする。`tailscale serve` が出す URL を開く）。外すときは `tailscale serve reset`。
- 確認メール・再設定メールのリンクは `BETTER_AUTH_URL`（localhost）のまま。外ではリンクの頭を入口の URL に読み替える。

## 2. GPU 機（Windows + RTX 4090、Docker Desktop + WSL2）

起動（GPU 機の作業ツリーで）:

```bash
docker compose -f compose.gpu.yaml --profile llm up -d
```

役割ごとに必要なものだけでもよい（例 `up -d tei-embed tei-rerank-ruri`）。`compose.gpu.yaml` の先頭のコメント参照。

| サービス | ポート | 確かめ方 |
|---|---|---|
| tei-embed | 8081 | `curl http://<GPU機>:8081/health` |
| tei-rerank-ruri | 8084 | `curl http://<GPU機>:8084/health` |
| docling-serve | 5001 | `curl http://<GPU機>:5001/health` |
| gemma（会話・補助・文脈付与・図の説明。Gemma 4 12B） | 8093 | `curl http://<GPU機>:8093/health`、`/v1/models` |

### VRAM

24GB に TEI・docling・gemma を同居させている。`nvidia-smi` で 24GB の近くまで使っていたら、`--kv-cache-memory-bytes`（`GEMMA_KV_BYTES`）を増やさない。超えても OOM にならず、共有メモリに追い出されて静かに遅くなる。

### コードの更新

GPU 機では push しない。Mac で変更を push し、GPU 機は `git pull` する。GPU 機の作業は、そこで動く Claude Code（Remote Control）に頼める。

## 3. 入庫・再索引・評価

評価と CLI は、開発用ヘッダで認証する api（127.0.0.1:8101）を使う。

```bash
make eval-api
cd api
uv run python -m arag.cli ingest-dir ../eval/assets/agentic_rag_demo --kb <KB の ID>   # まとめて入庫
uv run python -m arag.cli reindex --all          # 解析し直さずに再索引（--dry-run で対象だけ）
# 分割の版を上げたとき、結果の変わる文書が少なければ --content-hash で絞る（hybrid-md-v5 で変わるのは柱から章の決まる PDF だけ）
uv run python -m arag.cli gc                     # ごみ箱の期限切れと孤立した内容を回収
uv run python -m arag.cli sync-payload           # Qdrant の payload を DB に合わせる
uv run python -m arag.eval run --suite agentic_rag_demo --variant default dbsf   # 検索の評価
uv run python -m arag.eval answer --suite agentic_rag_demo_ext                  # 回答の評価
uv run python -m arag.eval answer --suite harukaze_clarify                      # 聞き返しの評価（harukaze_mix の KB を使う）
uv run python -m arag.eval answer --suite handbook_structure                    # 長い文書の構成（目次・最後の章）を続けて尋ねる評価
cd .. && make eval-api-down
```

- 題集は `eval/suites/`、構成の違いは `eval/variants.yaml`。指標と閾値は `specs/004-retrieval`・`specs/005-agent`。
- 埋め込みのモデルや次元を変えたら `ARAG_QDRANT_COLLECTION` を別名にして再索引する（次元が違うと入庫が止まる）。

## 3.1 模擬の社内システム（MCP。`specs/032`）

評価資料の会社（ハルカゼ精工）の ERP・保全システム・社員名簿・課題の管理を模擬で動かし、MCP サーバとしてエージェントにつなぐ。
データは `mock/systems/src/mock_systems/seed.py`（9/30 の値は harukaze_mix の台帳と一致、その後 11/18 までの動き）。

```bash
# .env に ARAG_MCP_IDENTITY_KEY（32 文字以上の乱数）を書いてから
make up-mock          # mock-systems（:8201〜8204）を起動し、4 つのサーバを登録（使える範囲は全員）
make down             # 止める（mock も含む）
```

- 登録・ツールの選択・使える範囲・接続の確認は管理画面の「社内システム」（`/admin/systems`）。変更は次の質問から効く。
- 利用者ごとに切るのは「社内システムも調べる」（設定）。オフなら記録に「社内システムを使わない設定」が残る。
- 権限は模擬の側で決まる: 仕入単価は資材係・購買課だけ、作業指示は保全課・製造課だけ、個人の携帯番号はだれにも出さない。
- 障害の注入（評価・確認用）: 起動時の `MOCK_FAULTS="cmms=down,erp=slow:15,tickets=deny"` か、動かしたまま

```bash
curl -s -X POST localhost:8201/_faults -H 'content-type: application/json' -d '{"cmms":"down"}'   # 止める
curl -s -X POST localhost:8201/_faults -H 'content-type: application/json' -d '{}'                # 戻す
```

- 社内システムの評価（harukaze_systems。KB は harukaze_mix を使う）:

```bash
cd api
uv run python -m arag.cli eval-users --suite harukaze_systems   # 評価用の利用者（部門・所属・KB の閲覧）
uv run python -m arag.eval answer --suite harukaze_systems --out ../eval/.reports/hs-gemma4-12b-032
```

題ごとの利用者（`as_user`）と障害（`faults`）は題集に書く。結果には期待したシステムを呼んだ率・権限の無い値の漏れ・
注意（時点・権限・停止）を書いた率が出る。

## 3.2 本物の ERP（Odoo）と大きい世界（`specs/033`・`specs/034`）

ERP を Odoo 18（外部のシステムとして compose の profile `erp` で動かす）にし、その前に ERP の MCP サーバ
（`mcp/erp/`、compose の `erp-mcp` :8211）を置く。データは模擬器（`sim/`）が 2026-04-01〜11-18 の業務の流れとして入れたもの
（部品 424・発注 1,475・入出庫 約 1 万 2 千）。名簿・保全・課題は模擬（`make up-mock`）のまま。

```bash
# .env に ERP_ODOO_SECRET（32 文字以上の乱数。Odoo の技術利用者のパスワードの元）を書いてから
make sim-odoo         # 初回だけ: Odoo を空から作り、模擬器の世界を入れてスナップショット（.data/erp/harukaze-034.dump、10 分前後）
make erp-reset        # スナップショットに戻す（評価の前に毎回）
make up-erp           # Odoo と erp-mcp を起こし、ARag の「erp」を erp-mcp に替える（ツール名 erp__* は同じ）
make up-mock          # 名簿・保全・課題（と模擬の ERP の登録）。ERP を模擬に戻すときもこれ
```

- 「今日」: erp-mcp の `ERP_TODAY`。空（compose の既定）なら実際の日付で、画面で見るとき（取得の時刻と「◯秒前」が本当になる）。
  評価は世界の日付で `ERP_TODAY=2026-11-18 make up-erp`（納期を過ぎたかの判定がこの日で決まる）。
- 模擬の ERP（SQLite）を erp-mcp で出す: `ERP_BACKEND=mock ERP_TODAY=2026-11-18 make up-erp`（`eval/assets/harukaze_plant/world.db` を読む）。
  Odoo と同じ答えになることは `mcp/erp` の契約のテスト（`ERP_ODOO_TEST=1 uv run pytest tests/test_contract.py`）が確かめる。
- 権限: 部門 → ERP の利用者は `mcp/erp/config/users.yaml`（購買課・資材係は erp-kobai、現場は erp-genba で仕入単価を伏せる、
  部門の無い人は erp-viewer で発注を見られない＝Odoo が拒否）。監査の行ログは erp-mcp の `/data/audit.jsonl`（volume `erp-audit`）。
- 世界・文書・答えを作り直す（決定的。種 `SIM_SEED`）:

```bash
cd sim
uv run python -m harukaze_sim sqlite ../eval/assets/harukaze_plant/world.db
uv run python -m harukaze_sim docs ../eval/assets/harukaze_plant/world.db ../eval/assets/harukaze_plant/docs
uv run python -m harukaze_sim answers ../eval/assets/harukaze_plant/world.db   # 題集の cases（根拠付き）
```

- 大きい世界の評価（harukaze_plant、35 題。KB は harukaze_plant の文書 8 つ）:

```bash
cd api
uv run python -m arag.eval ingest --suite harukaze_plant
uv run python -m arag.cli eval-users --suite harukaze_plant
uv run python -m arag.eval answer --suite harukaze_plant --out ../eval/.reports/hp-gemma4-12b-034-odoo
```

- 止まったとき: erp-mcp は Odoo が 3 回続けて失敗すると 30 秒だけ呼ばない（`unavailable`）。`docker compose --profile erp logs odoo erp-mcp`。

## 4. 回答を確かめる

- 「詳細」でエージェントの段階（検索・読む・計算・見直し）と、末尾の「システムの処理」（ツールの必須化・回数の上限・履歴の省略・回答の整形・要約）を見る。
- 数字は元の文書で確かめる（例 `eval/assets/harukaze_mix/docs/`。xlsx は openpyxl、pptx は python-pptx）。出典番号が付いていても、その資料に数字が無いことがある。

## 4.1 解析（Docling）を確かめる

回答の誤りが「Docling の抽出」「チャンク化」「文脈付与」のどれかを切り分ける（`specs/030-parse-inspection`）。

- 文書を開き「解析の確認」タブ: 左に原件の頁（PDF）とチャンクの枠、右にその頁のチャンクと、**Docling の抽出文・文脈・埋め込みに送った本文**。回答の出典パネルの「解析を確かめる」から、引用された章を選んだ状態で開ける。
- 警告のある頁には札が付く（空の頁・図だけの頁・文字化け・崩れた表・図の欠け・枠の頁外など）。ライブラリの詳細には警告の件数が出る。
- 記録は `contents/<hash>/parse_report.json`（docling-serve の status・errors・所要時間、頁ごとの数、警告）。Docling の生 JSON は管理者だけ `GET /v1/documents/{id}/docling`（画面の「Docling の JSON」）。
- 記録の無い古い文書は `docker compose exec worker python -m arag.cli reparse-report [--content-hash H]` で、保存済みの `docling.json` から作り直す（Docling は呼ばない）。位置を持たない図チャンクには、このとき図の位置も補う。
- 枠を重ねるのは PDF だけ。docx・xlsx・pptx はチャンクの一覧と 3 つの本文を見る。
- 切り分けの目安: 抽出文が原件と違う → Docling（OCR・表・読み順）。抽出文は正しいが枠や切れ目がおかしい → チャンク化。文脈が的外れ → 文脈付与。

## 5. よくある詰まり

| 症状 | 原因と対処 |
|---|---|
| 変えたはずのエージェントの動きが変わらない | 本番の構成（`make up-prod`）で動いている。`make up` で開発構成に戻すか、`docker compose -f compose.yaml up -d --build --no-deps runner`。開発構成なら `docker compose logs runner` に `change detected` が出ているか見る |
| 開発サーバから質問が送れない | 送信元を 3100 に限っている。3100 で確かめる |
| Tailscale の URL でログイン・質問が 403 | その入口が `ARAG_EXTRA_ORIGINS` に無い。足して `docker compose up -d web` |
| 回答がすぐ失敗する・モデルが切り替わる | GPU 機の vLLM が落ちている、または外部 API の残高切れ（402）。「詳細」のモデル切り替えのステップに理由が出る |
| 入庫が進まない | `worker` のログ、api の `/readyz`、docling-serve（5001）の `/health` を見る |
| `make gen-check` が CI で落ちる | API を変えて `make gen` をしていない |
