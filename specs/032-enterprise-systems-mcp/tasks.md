# 032 — タスク

状態: 承認済み（2026-11-19）・実装中。各項目は先に失敗するテストを書く。

## A. 模擬の社内システム（`mock/systems/`）

- [x] T1 `mock/systems/` の骨格（uv の別プロジェクト・Dockerfile・compose の `mock-systems`（`--profile mock`）・SQLite を読み取り専用で開く）
- [x] T2 模擬のデータの生成（`mock_systems/seed.py` → SQLite）。`test_seed_matches_assets`: 9/30 の値が harukaze_mix の xlsx と一致 — R1〜R3
- [x] T3 見せない列・行と、指示に見える文の行 — R4・R5
- [x] T4 4 つの MCP サーバとツール（FastMCP・Streamable HTTP・`readOnlyHint`）。ツールごとのテスト — R6
- [x] T5 身元の検証（JWT・`aud`・期限）と権限で列・行を絞る。`forbidden` の返し方 — R13・R16
- [x] T6 障害の注入（`MOCK_FAULTS`・`/_faults`） — R7

## B. 登録（api・管理コンソール）

- [x] T7 移行 0010（`mcp_servers`・`mcp_tools`・`mcp_server_shares`）と目録の指紋（`catalog_key`。版の値は持たない） — R8〜R11
- [x] T8 管理 API（登録・編集・削除・ツールの取り直し・ツールの選択・使える範囲）と監査。読み取り専用の印の無いツールは選べない — R8〜R11
- [x] T9 `arag.cli mcp-register`（模擬の 4 サーバを入れる）と `make up-mock` — R8
- [x] T10 管理コンソールの「社内システム」タブ — R8〜R10

## C. エージェント

- [x] T11 依存を足す（`mcp`）。`licenses.md`・`make licenses`
- [x] T12 `agent/mcp_tools.py`（接続は `mcp/client.py`）: ツールの読み込み・`McpTool` の包み（身元・待ち時間・回数・切り詰め・`forbidden`・データの囲み） — R12・R13・R17〜R19
- [x] T13 runner の `agent_cache` の鍵に目録の版。run の開始時の使える集合（共有リスト・利用者の設定・死活）と、`AgentPolicyMiddleware` での絞り込み — R10・R12・R14・R17
- [x] T14 システムの処理の記録（`mcp_filtered`・`mcp_unavailable`・`mcp_timeout`・`mcp_denied`・`mcp_truncated`・`mcp_limit`・`mcp_off`） — R24
- [x] T15 プロンプト（根拠の範囲・時点・権限・止まっているとき。使えるシステムがあるターンだけ） — R15〜R18
- [x] T16 偽モデルのテスト: 呼んで引用する・範囲で外す・止まっていれば外す・回数の上限・`make graph` で流れが変わらないこと — R12・R17・R25

## D. 出典と画面

- [x] T17 `Cited.source_kind`・`RecordRef`・出典の登録。確認（数字の照合・理由・章の見出し）の資料にシステムの結果を含める — R20・R21
- [x] T18 `CitationOut` の拡張と `make gen`。共有ページで行を伏せる — R20・R22
- [x] T19 出典カード（システムの札・条件・時刻・行の表）、`FileTile kind="system"`、見本（`/dev/ui`） — R20
- [x] T20 「詳細」のツールの入出力と、システムの処理の表示（`step-input`・`step-output`・`system-fields`・`chat.ts`） — R23・R24
- [x] T21 利用者の設定「社内システムも調べる」 — R14

## E. 評価と確認

- [x] T22 評価の拡張: 題の `as_user`・`faults`・`must_not`・`expect_tools`・`expect_caveat`。`arag.cli eval-users` — R27・R29
- [ ] T23 題集 `harukaze_systems`（30 題前後。題は 1 問ずつ利用者と確かめて確定する。018 R5 と同じ） — R26
  - 候補 30 題を書いた（2026-11-19、`eval/suites/harukaze_systems/golden.yaml`・利用者は `eval/assets/harukaze_systems/users.yaml`）。利用者の確認待ち
- [ ] T24 harukaze_systems を Gemma 4 12B で流し、結果を `eval/.reports/hs-gemma4-12b-032` に出す — R29
- [ ] T25 harukaze_mix を社内システムの無い状態・有る状態で流して比べる — R28
- [x] T15b 今の値を問う質問: 検索結果の外の注意（`current_note`）と、システムを呼ばずに答えた下書きの差し戻し（`current`）。偽モデルのテスト — R15
- [x] T15c 試走の弱点: 記録を問う語（仕入単価・作業指示・最近）も確かめさせる・「いま」の誤検出・応答しないシステムをプロンプトに書く・模擬の課題の一覧に最新の経過。テスト — R15・R17
- [x] T15d 全 30 題の試走の弱点: システムの説明をプロンプトに・文書に無いと答えた下書きの差し戻し（`system_gap`）・終わりましたか / been resolved・評価で障害の後に死活の記憶を待つ・`expect_tools` の「a|b」。テスト — R15・R26
- [ ] T26 3100 で実際に確かめる（権限のある人と無い人・止まっているとき・出典カードと「詳細」）。`make up-prod` でも一度見る
- [x] T27 `docs/operations.md` に模擬の起動・登録・障害の注入の手順、`AGENTS.md` の地図に `mock/` を足す
