# 003 入庫（P1）— タスク

各タスクは失敗するテストを先に書く。（ ）は対応テスト・確認手段、末尾は要件番号。担当: **Mac** = この会話、**Win** = GPU 機の会話。

## A. 基盤
- [x] A1 Mac: 依存追加と licenses.md 追記（`make licenses` が通る）— design §9
- [x] A2 Mac: Alembic 0001（app スキーマ・全表・部分 UNIQUE）（integration: upgrade/downgrade 往復）
- [x] A3 Mac: `Principal` と dev ヘッダ認証、`ARAG_AUTH_MODE` 以外では無視（test_principal）— R1・R2
- [x] A4 Mac: 共通エラー応答 `{"error":{code,message}}`（test_errors）
- [x] A5 Mac: `LocalStorage`（put / open_range / delete_prefix、パス脱出の拒否）（test_storage）— R12
- [x] A6 Mac: `write_audit`（test_audit）— R36

## B. KB・フォルダ・権限
- [ ] B1 Mac: 権限の純関数（個人/全社 × owner/admin/member × read/write/purge の表駆動テスト）— R4〜R6・R34
- [ ] B2 Mac: 個人 KB の自動作成（integration: 並行 10 要求で 1 件）— R3
- [ ] B3 Mac: KB API（作成・名前変更・アーカイブ・削除・復元、権限外は 404）— R4〜R6
- [ ] B4 Mac: フォルダ API（同名 409・循環移動 400・削除の再帰・復元で祖先も復活）— R32・R33

## C. アップロード
- [ ] C1 Mac: 形式判定と上限（415 / 413）— R11
- [ ] C2 Mac: 内容ハッシュ dedup（queued / skipped / duplicate）— R7・R8
- [ ] C3 Mac: 並行初回アップロードで原本・ジョブが 1 回（integration）— R9
- [ ] C4 Mac: 相対パス → フォルダ自動作成 — R10

## D. パイプライン部品（純関数・偽依存）
- [ ] D1 Mac: `PlainTextParser`（TXT / JSON / CSV / MD）— R16
- [ ] D2 Mac: `DoclingServeParser`（偽 HTTP サーバで: 非同期タスクのポーリング、ページ窓の分割と結合、タイムアウト）— R14・R15・R28
- [ ] D3 Mac: chunking（fixture JSON: セクションのまとめ方・上限分割・見出し無し文書・表ヘッダ繰り返し・block_type・boxes）— R17・R18
- [ ] D4 Mac: sparse（型番・条項番号が 1 語で残る、助詞が消える、同じ入力で同じ ID、tf 飽和の値）— R22
- [ ] D5 Mac: contextualize（`FakeListChatModel` で: 出力の格納、失敗時のフォールバック、usage 合計、文書全文の上限）— R20・R21
- [ ] D6 Mac: 図の説明（小さい画像の除外、無効時はキャプションのみ）— R19
- [ ] D7 Mac: TEI クライアント（バッチ分割・再試行）
- [ ] D8 Mac: Qdrant index（コレクション作成の冪等性、upsert、`sync_payload` で削除文書が外れる）（integration）— R23

## E. パイプラインとワーカー
- [ ] E1 Mac: `run_ingest` の段階遷移と progress（偽依存）— R13
- [ ] E2 Mac: 冪等な再実行（前回のチャンク・点が残らない）— R25
- [ ] E3 Mac: 取消（段階の境目で止まり cancelled）・再試行（attempts リセット）— R26
- [ ] E4 Mac: 自動再試行と error 確定、利用者向けメッセージとログ詳細の分離 — R24
- [ ] E5 Mac: 起動時の途中ジョブ再投入 — R27
- [ ] E6 Mac: 進捗 SSE（購読→現状→差分の順、権限外ジョブを返さない、全終端で閉じる）— R29・R30
- [ ] E7 Mac: GC（保持期間超過・ref_count 0 の実体削除）（integration）— R35

## F. 文書 API
- [ ] F1 Mac: 一覧（フォルダ・状態・カーソル、書込可否）・統計 — R31
- [ ] F2 Mac: 名前変更・移動・一括移動・一括削除・削除・復元・完全削除（24h 規則）— R32〜R34
- [ ] F3 Mac: 原本（Range）・rendered・outline・sections・chunks・assets — R37・R38
- [ ] F4 Mac: ごみ箱一覧（残り日数つき）

## G. 運用・実データ
- [ ] G1 Win: `compose.gpu.yaml` に docling-serve（cu130, :5001）を追加し、評価用 PDF 1 件の変換時間・GPU メモリを測る。日本語 OCR エンジンの比較（スキャン PDF 2〜3 件）— design §10-1
- [ ] G2 Mac: `/readyz` に docling-serve を追加 — R40
- [ ] G3 Mac: `cli reindex` / `cli ingest-dir` — R41
- [ ] G4 Mac: 評価用 PDF 7 件を `eval/assets/agentic_rag_demo/` に複製し、fixture JSON を作成
- [ ] G5 Mac+Win: E1〜E5（requirements「完了の確認」）を GPU 機のサービスに向けて実行し、結果（所要時間・チャンク数・文脈付与の費用）を `specs/003-ingestion/report.md` に記録
