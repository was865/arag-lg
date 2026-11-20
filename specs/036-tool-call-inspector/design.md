# 036 社内システムの呼び出しを技術者が確かめられる表示 — 設計

## 1. MCP サーバ（`mcp/erp`・`mock/systems`）

- `querylog`: 呼び出しごとの記録の入れ物を ContextVar で持つ。
  `Service.call`（ERP）・`_call`（模擬）が始めに空の入れ物を置き、終わりに trace の `queries` へ移す。
  件数と字数の上限（30 件・4000 字）を超えた分は `queries_dropped` に数だけを書く。
- SQLite: 接続に `set_trace_callback` を付け、値を埋め込んだ文（SQLite が展開する）を記録する。
  模擬の 4 システムの読み取りの接続も同じ。
- Odoo: `_x`（`execute_kw` の包み）で、model・method・位置の引数（domain）・名前付きの引数（fields・limit・offset・order。
  context は除く）・ミリ秒・件数（戻り値が list なら長さ、数ならその値）を記録する。
  - 認証（`common.login`）は `_x` を通らないので記録されない。
  - 表示用の文は `product.product.search_read([...], fields=[...], limit=80)` の形にする。
- 記録の形: `{"lang": "sql"|"odoo", "text": str, "ms": float|None, "rows": int|None}`。

## 2. ARag（`api/src/arag/agent/mcp_tools.py`）

- 段階の出力（`table_outputs`）に次を足す。
  - `server`・`tool`（MCP のツール名）・`args`
  - `rtt_ms`: ARag が測った往復
  - `model_text`: モデルに返した文（出典の囲みを含む。最大 8000 字）
- trace（queries を含む）は今までどおり通す。
- 表でない結果（`columns` が無い）も、`server`・`tool`・`args`・`rtt_ms`・`model_text` を段階の出力に残す。

## 3. 画面（`web/src/components/chat/tool-steps/system-call.tsx`）

- `SystemCallView`: 社内システムの段階の入力と出力をまとめて 1 つにする（入力の欄は出さない）。
  - 1 行目: 呼び出しの式（等幅・写すボタン）
  - 2 行目: 時間の内訳の細い帯（サーバの中・通信と整形）と数字。問い合わせの回数・使い回し・ERP の利用者
  - 切り替え（`Segmented`）: 結果 / 問い合わせ N / MCP / モデルに渡した文
- `ui/code-block.tsx`: 等幅の文の面（言語の札・写すボタン・長い文は高さを抑えて中で滑らせる）。
  SQL・Odoo の語は控えめに色を付ける（accent は使わない。キーワードは fg、文字列は muted）。見本（/dev/ui）に足す。
- 純関数（`web/src/lib/chat/system-call.ts`）: 呼び出しの式・時間の内訳・SQL の語の分け方。テストする。

## 4. 実装で決めたこと（2026-11-21）

- 問い合わせの面は、1 行ずつの滝にする。各行は番号・種類・文の頭・最も長い問い合わせを基準にした時間の帯・時間・件数。
  開くと文の全体とコピー（list_below_reorder は Odoo の問い合わせが 15 件あり、全部を広げると長すぎた）。
- 札の「問い合わせ N 回」は記録した件数を使う（サーバの calls は数え方が粗く、記録と合わないことがあった）。
- 結果の面では、ツールと引数を上の式と重ねて出さない。
- 確かめ: 3100 の名簿の SQL を写して読み取り専用の DB で流し、同じ 1 行（佐伯 美穂・2210）が返った。
