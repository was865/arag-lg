# 022 スレッドの本文検索 — 設計

## API（`api/src/arag/agent/thread_search.py`・`router.py`）

- 語ごとに `Thread.title ILIKE p OR EXISTS(Message.query ILIKE p OR Message.answer_text ILIKE p)` を作り、AND でつなぐ。
  `p` は `%`・`_`・`\` を `\` で逃がした `%語%`（`ESCAPE '\'`）。語は最大 8 個、重複は除く。
- 対象のスレッドを `updated_at` の新しい順に `limit`（既定 20・最大 50）件取り、そのメッセージを読んで当たった場所と前後の文を Python で決める（R2）。
- 規模: 1 人のスレッドは多くて数千、メッセージも数万の想定で、全文索引（pg_trgm など）は入れていない。遅くなったら `pg_trgm` の GIN 索引を足す。
- `/v1/threads/{thread_id}` より前に宣言する（`search` を id と読まないため）。

## 画面（`web/src/hooks/use-thread-search.ts`・`components/sidebar/sidebar-search-results.tsx`）

- `useThreadSearch(q)`: 250ms 待って呼び、前の問い合わせは `AbortController` で中止する。結果は「どの語の結果か」と組で持ち、今の語と違えば検索中とみなす。
- 強調は `highlightParts`（長い語から当て、正規表現の記号は逃がす）。
