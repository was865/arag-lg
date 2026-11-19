# 033 本物の ERP（Odoo）につなぐ ERP の MCP サーバ — 設計

状態: **承認済み（2026-11-20）**。

## 1. 全体

```
ARag（runner）                         同じ compose（profile erp）／本番では ERP の隣の内網
  agent/mcp_tools ──HTTP + 身元 JWT──▶ erp-mcp（mcp/erp/、FastMCP、Streamable HTTP）
  （032: 登録・待ち時間・切り詰め・      ├ 入口: JWT の確認（aud・exp・kid）・trace-id・呼び出しの監査
    記録・出典はそのまま）              ├ ツール: 業務の単位（§3）。汎用の問い合わせ・SQL・書き込みは無い
                                       ├ 方針: 部門 → ERP の利用者、伏せる列の印、件数の上限
                                       ├ アダプタ（ErpBackend）: odoo ／ mock（032 の SQLite）／（後で sap_odata・kingdee）
                                       └ 運用: 接続の使い回し・同時数の上限・続けて失敗したら止める・10 秒の使い回し・/health
                                                  │ JSON-RPC（/jsonrpc、execute_kw）
                                         Odoo 18 Community（odoo:18 の image、専用の postgres）
```

- `mock/systems` の ERP（032）は消さない。評価の再現のため、`erp-mcp` の **mock アダプタ**が同じ SQLite を読む形に寄せる。
  保全・名簿・課題の模擬（cmms・directory・tickets）は 032 のまま残す（保全は §3.3 のとおり後で Odoo に寄せられる）。
- ARag の側は 032 の仕組み（登録・使える範囲・身元・記録・出典）をそのまま使う。足すのは R15〜R21 の分だけ。

## 2. アダプタ（端口）

```python
class ErpBackend(Protocol):
    async def find_parts(self, who: ErpUser, term: str, page: Page) -> Rows
    async def get_stock(self, who: ErpUser, part: str) -> Rows
    async def list_stock_moves(self, who: ErpUser, part: str, since: date | None, until: date | None, page: Page) -> Rows
    async def list_purchase_orders(self, who: ErpUser, q: PoQuery, page: Page) -> Rows
    async def list_sales_orders(self, who: ErpUser, q: SoQuery, page: Page) -> Rows
    async def list_suppliers(self, who: ErpUser, term: str) -> Rows
    async def health(self) -> Health
```

- `Rows` は列・行・総数・伏せた列・続きの手がかり。ツールの層が 032 の出力の形にする（`basis` は「Odoo の現在の値（… 取得）」）。
- 項目の対応は `mcp/erp/config/<erp>.yaml`（例 Odoo: 部品 = `product.product`、在庫 = `stock.quant` を倉庫で絞る、
  発注 = `purchase.order.line`、入出庫 = `stock.move.line`、発注点 = `stock.warehouse.orderpoint`）。
  使える倉庫（呆滞・見本の倉庫を在庫に数えない）・単位の扱いもここに書く（金蝶の実測の教訓）。
- 問い合わせの条件（Odoo の domain）は、型の付いた引数から組み立てる。利用者の語は `ilike` の値としてだけ使う（R4）。
- ページ送り: `search_read` の `limit`/`offset` で上限（既定 2,000 行）まで取る。超えたら `too_many`（総数と絞り込みの手がかり）（R5）。
- 契約のテスト（`tests/contract/`）を両方のアダプタで回す: 同じ問いに同じ列・同じ型・同じ並び。値は 034 の同じ種から作るので一致する。

## 3. ツール

### 3.1 ERP（最初に作る）

| ツール | 引数 | 中身 |
|---|---|---|
| `find_parts` | 語・状態 | 部品番号・名称・適用・標準単価・発注点・仕入先・状態（廃止・後継） |
| `get_stock` | 部品 | 倉庫ごとの在庫・使える在庫・発注点との比較・未入荷の数 |
| `list_stock_moves` | 部品・期間 | 入庫・出庫・廃棄・棚卸 |
| `list_purchase_orders` | 部品・仕入先・状態・期間・納期遅れ | 発注番号・数量・入荷済みの数・納期・状態・仕入単価（権限のある人だけ） |
| `list_sales_orders` | 顧客・部品・状態・期間 | 受注・出荷済みの数・残り・納期 |
| `list_suppliers` | 語 | 仕入先・所在地・リードタイム・担当 |

### 3.2 説明の書き方

- 各ツールの説明に「何を問われたら使うか」と「何は出さないか（例: 単価は出さない → `list_purchase_orders`）」を書く（032 の試走の教訓）。
- MCP サーバの `instructions` とサーバの説明（ARag の管理画面に出る）は、この ERP に何があるかを 1 行で書く。

### 3.3 後で

- 保全（Odoo の `maintenance.equipment`・`maintenance.request`）を `cmms` の Odoo アダプタにする。
- 受注から出荷の予定の見通し（回交期の簡単版）。

## 4. 身元と権限

- ARag の JWT（032: HS256・`aud`=サーバ名・60 秒）に `kid` を足し、MCP サーバは複数の鍵を受け付ける（鍵の入れ替え）。
- 部門 → ERP の利用者の対応は `mcp/erp/config/users.yaml`（例 購買課 → `erp-kobai`、製造課 → `erp-seizo`、該当なし → `erp-viewer`）。
  Odoo の側は利用者ごとの API キーと権限の組（`purchase.group_purchase_user` など）で見える範囲が決まる（R9）。
- Odoo が読ませない項目は、Odoo の `fields_get` で読めるかを先に確かめ、読めない列は `restricted` に入れて空にする（R10）。
  読もうとして拒否されたとき（`AccessError`）は `forbidden` として返す（032 と同じ扱い）。
- 監査は MCP サーバの JSON の行ログ（`audit.jsonl`。本番は収集の仕組みへ）（R11）。

## 5. 運用

- 接続: `httpx.AsyncClient` を 1 つ持ち回す（Odoo への keep-alive）。ARag の `mcp/client.py` も、サーバごとに
  `httpx.AsyncClient` を使い回す（今は呼び出しのたびに作る）。MCP の `initialize` は呼び出しごとのまま（stateless の形）（R15）。
- 同時数の上限（既定 4）・待ち時間（既定 8 秒）・続けて 3 回失敗したら 30 秒止める（R12）。
- 使い回し: `(ERP の利用者, ツール, 引数)` の鍵で 10 秒。`fetched_at` は元の取得の時刻（R13）。
- `GET /health`: Odoo の `version` と簡単な `search_count` の所要時間（R14）。

## 6. 画面（今の値の実感）

作った動き（偽の点滅・流れる文字）は出さない。出すのは本当の時点・本当の状態・本当の差だけ。

- **取得の時点**（R16）: `SystemRecordView` とカードに「12 秒前」（1 分ごとに更新。`web/src/lib/datetime.ts` に `ago()` を足す）と時刻。
- **最新にする**（R17）: 右の面のシステムの記録に「最新にする」。新しい口 `POST /v1/messages/{id}/systems/{n}/refresh`
  が runner を通さず、同じ利用者の身元で同じツール・引数を呼ぶ（api に MCP の呼び出しを持たせる。`mcp/client.py` を共用）。
  結果は前の値と並べ、変わった欄に印（増減の矢印）。呼び直しはメッセージの記録に `mcp_refresh` として足す（後から追える）。
- **問い合わせ中**（R18）: 032 の running の段階（「ERP に問い合わせ中」）に、ツール・引数と経過の秒を出す。終わったら「12 行・0.8 秒」。
- **接続の状態**（R19）: runner の死活の結果（032 の `HealthCache`）を redis にも書く（30 秒）。api の `GET /v1/systems/status`
  が、その利用者が使えるシステムと状態（ok・slow（2 秒超）・down）を返す。入力欄の「社内システム」の札に小さな印。
- **時点の比較**（R20）: 回答の後処理で、同じ項目に文書の出典とシステムの出典が両方付いた数字の組を見つけたら、
  「時点の比較」の小さな表を回答の下に出す（判定はコード。見つからなければ出さない）。
- **管理の数字**（R21）: MCP サーバの監査ログではなく、ARag 側の記録（ステップの所要時間・種類）から集計する（`/v1/admin/mcp-servers/{id}/stats`）。

## 7. 書き戻し（設計だけ）

- 流れ: エージェントは「提案」（対象・項目・新しい値・理由）を返すだけ → 画面の確認の札 → `POST /v1/actions/erp/{kind}` →
  MCP サーバの書き込み専用の口（ツールとしては出さない）→ 書く前の値（Odoo の `write_date` か項目の値）を確かめて 1 項目だけ書く。
- 最初の候補: 発注の「納期の予定」（`purchase.order.line.date_planned`）。書く前の値と書いた人を記録し、元に戻せる。

## 8. compose と Odoo

- `compose.yaml` に `odoo`（`odoo:18`）・`odoo-db`（postgres）・`erp-mcp` を profile `erp` で足す。ポート: Odoo :8069、erp-mcp :8211。
- 入れるモジュール: `stock`・`purchase`・`sale_management`・`maintenance`（後で）・`l10n_jp`。
- 種のデータは 034 の模擬器が Odoo の API で入れ、終わったら `pg_dump` でスナップショット（`eval/assets/erp/odoo-snapshot.dump`、
  大きければ git に入れず作り方だけを置く）。`make erp-reset` が戻す（R23）。
- `make up-erp`: Odoo と erp-mcp を起こし、ARag に MCP サーバとして登録する（032 の `mcp-register` に `--erp` を足す）。

## 9. 確かめ方

- 単体: アダプタの domain の組み立て（注入できない）・ページ送り・`too_many`・伏せる列・失敗の数え方。
- 契約: mock と Odoo で同じ答えの形（Odoo は compose で起こした結合テスト。CI では mock だけ）。
- 評価: harukaze_systems を `--variant erp-odoo` で流す（`eval/.reports/hs-gemma4-12b-033-odoo`）。
- 3100 で: R16〜R20 を実際に見る。デモの台本（R25）を一度通す。

## 10. 採否

- **Odoo を選ぶ**: 無料で立つ・業務の流れが本物・API と権限が本物・日本語。ERPNext は GPL-3.0 なので選ばない。
  Odoo は LGPL-3.0 だが、製品に含めず外から呼ぶだけ（R26）。
- **MCP サーバは Python（FastMCP）**: 032 の模擬と同じ。Odoo の API は JSON-RPC なので、新しい依存は要らない（httpx）。
- **langchain-mcp-adapters は使わない**（032 と同じ理由）。
