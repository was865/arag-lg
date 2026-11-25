# 037 エージェントの層の整理 — 要件

状態: 実装済み（2026-11-25）。R13 は試したが採用しない（tasks.md T7）。

エージェント（`api/src/arag/agent/`）は、判断の規則・処理の流れ・LangChain / SQLAlchemy の技術が同じファイルに混ざり、
次の問題があった（2026-11-21 の見直し）。

- 確認（差し戻し）の規則が、ツールの結果の**文**を正規表現で読んで判断していた（モデルに見せる文が、モジュールの間の取り決めを兼ねる）。
  文言を変えると確認が黙って効かなくなる。
- 確認の種類ごとに数える欄が `RunStats` に 8 つあり、種類を足すたびに 4 か所を直す。「章の見出しの確認」は数え先が無く、
  数字の確認として数えていた。
- ツールの中身（`ops.py`）が SQLAlchemy で直接 DB を読み、文書の読み出しを偽物に替えて確かめられない。
- 社内システム（`arag.mcp`）の中核がエージェント（`arag.agent`）を import し、依存が循環していた。

回答の中身・記録のステップ・画面は変えない（純粋な整理）。既存のスナップショット（`test_agent_flow_snapshots.py`）が一致すること。

## 1. 依存の向き

- R1. `arag.mcp` の中核（`client`・`registry`・`service`・`live`）は `arag.agent` を import しない。
  HTTP の口（`*router.py`）は他の区分の service を使ってよい。
- R2. `arag.search` は `arag.agent` を import しない。エージェントは検索の実装（`search.service`）ではなく、
  型（`search.schemas`）・範囲（`search.scope`）・計測の口（`search.hooks`）だけに依存する。
- R3. 純粋な規則のモジュール（引用・数字・表・計算・回答の文・確認の規則）は LangChain・LangGraph・SQLAlchemy・FastAPI を import しない。
- R4. R1〜R3 はテスト（`api/tests/test_layering.py`）が import を走査して守る。

## 2. ツールの結果の構造

- R5. 資料を返すツール（search・keyword_search・read_document・read_section・get_outline・table_query）は、
  モデルに渡す文に加えて、構造化した結果（資料の数・省略の有無・関連度の低さ・補った検索の種類・表の行数）を
  `ToolMessage.artifact` に載せる。
- R6. 確認・記録のステップの要約は、ツールの結果の構造を読んで判断する。モデルに渡す文の言い回しを読まない。
  構造が無い結果（この変更の前の checkpoint）は、資料なし・省略なしとして扱う。
- R7. システムが最初に行う検索（primer）も同じ構造で、関連度の低さを判断する。

## 3. 確認の規則

- R8. 確認（差し戻し）の規則は、種類・表示名・判断の関数の並びとして 1 か所に登録する。並びの順に確かめ、
  最初に当てはまった 1 つで差し戻す（今の順を変えない）。
- R9. 確認の規則は、会話のメッセージ（LangChain の型）ではなく、このターンの記録を写した値（ツールの名前・文・状態・構造）を受け取る。
- R10. 差し戻しの回数は種類ごとの辞書で数える。種類を足すときに数え先を足さなくてよい。
  章の見出しの確認は `structure` として数える。

## 4. 文書の読み出しの口

- R11. ツールの中身は、文書の読み出し（範囲の中の文書・章・表のシートの続き・最近の文書・名前の照合）を
  `DocumentStore` の口を通して行う。本番の実装は SQLAlchemy（`SqlDocumentStore`）、テストでは偽物に替えられる。

## 5. runner

- R12. 使っていない import（`flow.classify`）を外す。run の要求から実行文脈を作る処理を関数に分ける。

## 6. 検索の口と物理的な配置

- R15. 検索の口（`SearchFn`）は DB の session を受け取らない（`(principal, request)`）。session は実装の側で開く。

- R13. 社内システムの「今の値を問う語」（在庫・発注点・内線など）をコードの正規表現から外し、MCP サーバの登録の情報
  （説明・例の質問）と補助モデルの判断に移す。評価（harukaze_mix と 032 の題）で比べてから行う。
  → 補助モデルの判断に移す案は、評価で悪くなったので採用しない（tasks.md T7）。語の一覧は `domain/system_questions.py` に残す。
  次に試すなら、語を登録の情報（サーバごとの「今の値の語」）として管理画面で持たせ、コードの既定の語と合わせて使う。
- R14. 規則のモジュールを `agent/domain/`、DB・Redis・checkpoint の実装を `agent/adapters/` へ物理的に移す。処理の層は `adapters` を import しない（R4 の検査に足す）。
