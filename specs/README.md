# 仕様の一覧

機能ごとに `<番号>-<名前>/{requirements,design,tasks}.md`。新しい機能は次の番号で起こし、ここに 1 行足す。
requirements は EARS（「〜のとき、システムは〜する」）、tasks は印を付けられる小さな項目で、それぞれテストに対応させる。

| 番号 | 内容 |
|---|---|
| [000](000-overview/README.md) | 全体像: 機能・画面・API・データモデル・採否・ライセンス台帳 |
| [001](001-p0-skeleton/) | 骨格（monorepo・compose・CI・OpenAPI の型生成） |
| [002](002-tei-verification/) | TEI の数値一致の検証 |
| [003](003-ingestion/) | 入庫（Docling・父子の分块・文脈付与・内容ハッシュ・ごみ箱） |
| [004](004-retrieval/) | 検索（Qdrant の混合検索・rerank・検索の評価） |
| [005](005-agent/) | エージェント（ツール・middleware・後ろで実行する run・回答の評価） |
| [006](006-auth/) | 認証（Better Auth） |
| [007](007-document-viewer/) | 文書ビューア |
| [008](008-thread-share/) | スレッドの共有 |
| [009](009-library-bulk/) | 文書ライブラリの一括操作 |
| [010](010-admin-members/) | メンバー管理 |
| [011](011-audit-log/) | 監査ログ |
| [012](012-analytics/) | 利用状況の分析 |
| [013](013-llm-keys/) | LLM の接続（API キー）とモデル目録 |
| [014](014-settings/) | 設定パネル |
| [015](015-help-onboarding/) | ヘルプと初回ガイド |
| [016](016-inference-modules/) | 推論の構成を部品ごとに選ぶ（GPU 機の報告・VLM の比較を含む） |
| [017](017-query-image/) | 質問に画像を添える |
| [018](018-eval-corpus-mix/) | 評価用資料の拡充（形式混在・多ターン） |
| [019](019-cross-lingual-rerank/) | 日英をまたぐ検索 |
| [020](020-answer-special-provisions/) | 規程の特例・表の一部の集計 |
| [021](021-eval-wrong-facts/) | 回答評価で誤りの値を見る |
| [022](022-thread-search/) | スレッドの本文検索 |
| [023](023-kb-overview/) | ナレッジベースの概要 |
| [024](024-kb-access/) | 部門とナレッジベースの利用範囲 |
| [025](025-ui-motion/) | 外観 v2 と動き（複雑な検索の見直し・記録の階層表示を含む） |
