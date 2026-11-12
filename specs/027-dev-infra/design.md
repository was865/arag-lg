# 027 設計

## 1. 全体

```
仕様（specs/NNN）──▶ テスト（R 番号を参照）──▶ 実装 ──▶ PR
                                                      │
        ┌────────────── CI ───────────────────────────┤
        │ fast（全 PR、<10 分）                         │
        │   lint / 型 / 単体 / gen-check / licenses     │
        │   spec-lint / commit-lint / gitleaks          │
        │ integration（全 PR）: 結合テスト・compose smoke│
        │ eval-smoke（該当パスの PR）: 検索評価 + 門     │
        └───────────────────────────────────────────────┘
main ──▶ nightly（自前ランナー）: 回答評価 → 基準と比較 → 門 → 報告
tag  ──▶ release（設計のみ）: イメージ → SBOM
```

## 2. 仕様の道具（`scripts/spec_lint.py`、標準ライブラリだけ）

- 入力: `specs/[0-9]*/`。`000-overview`・`002`（報告だけ）など、形の違う古い仕様は `specs/.speclint.toml` の `legacy` に列挙して形の検査を外す。
- 検査:
  1. 3 ファイルがある。`requirements.md` の先頭 10 行に `状態: <draft|approved|implemented|superseded>（YYYY-MM-DD）`。
  2. 要件は `- R<n> ` で始まる行。番号の重複なし。
  3. `tasks.md` の `- [ ]` / `- [x]` の各項目に `R<n>` の参照がある（「— R1・R2」の形。既存の書き方）。
  4. 状態が implemented のとき: `api/tests`・`web/src` のテストから `specs/<番号> R<n>` を探し、参照の無い要件を列挙。
     最初は警告（終了コード 0）、`--strict` で失敗。新しい仕様（027 以降）は strict。
- 出力: 仕様ごとの表（要件数・参照のあるテスト数・欠け）。`--json` で CI の要約に使う。
- 雛形 `specs/_template/` と `make spec name=<名前>`（次の番号で複製し、`specs/README.md` に 1 行足す）。

## 3. 変更の流れ

- trunk-based。作業は `feat/<名前>`・`fix/<名前>`、PR でマージ（squash）。main の保護: 必須の検査 = fast・integration（eval-smoke は該当時のみ必須）。
- `.github/pull_request_template.md`: 仕様 / 変更の要点 / 確かめた方法 / 評価（`arag.eval diff` の表を貼る）/ 記録に出したか（AGENTS.md の原則）。
- commit-lint: `scripts/commit_lint.py`（標準ライブラリ。`type(scope)?: 本文`、type は feat/fix/docs/refactor/test/chore/perf/ci/build）。PR では `git log origin/main..HEAD` を検査。
- 秘密の検査: gitleaks（MIT）。`.gitleaks.toml` で `.env.example` と評価資料を除外。
- 依存の更新: Dependabot（GitHub 標準。週次、uv / npm / actions / docker）。脆弱性: `pip-audit`（Apache-2.0）と `pnpm audit --prod` を週次の workflow で。

## 4. CI（`.github/workflows/`）

| ファイル | きっかけ | 中身 | 目安 |
|---|---|---|---|
| `ci.yml`（既存を整理） | PR・main | fast: api（ruff・mypy・pytest の単体）/ web（eslint・tsc・vitest・build）/ gen-check / licenses / spec-lint / commit-lint / gitleaks。integration: infra を立てて結合テスト、compose smoke | 10 分 |
| `eval-smoke.yml` | PR（paths: agent・search・ingest・prompts・eval） | CPU の TEI（`--profile cpu`）で `agentic_rag_demo` を入庫し、`arag.eval run --gate`。指標を PR の要約に書く | 15 分 |
| `nightly-eval.yml` | cron（JST 03:00）・手動（model を選ぶ） | 自前ランナー（ラベル `arag-eval`）。`make up` 済みの環境で `arag.eval answer --suite harukaze_mix --model <id> --gate`。レポートを artifact に。失敗したら issue を起こす（同じ題名があれば追記） | 10 分 |
| `audit.yml` | 週次 | pip-audit・pnpm audit。見つかれば issue | 3 分 |
| `release.yml`（設計のみ） | tag `v*` | api・web のイメージを ghcr に、syft（Apache-2.0）で SBOM を付ける | — |

- 単体と結合を分ける: pytest の marker `integration`（既存）で、fast は `-m "not integration"`、integration は `-m integration`。
- キャッシュ: uv（`~/.cache/uv`）・pnpm store・docker layer（buildx の gha キャッシュ）。
- 自前ランナー: Mac（compose の全体と、Tailscale 越しの GPU 機が見える）に GitHub Actions runner を 1 台。
  公開リポジトリの fork からは動かさない（`if: github.event_name != 'pull_request'`）。GPU 機が落ちているときは「skipped（推論なし）」として失敗にしない（readyz で判定）。

## 5. 評価の仕組み

### 層

| 層 | 何を | いつ | 門 |
|---|---|---|---|
| L0 契約 | 偽モデルでの流れ・ステップ・イベント | 全 PR（単体） | 失敗で止める |
| L1 検索 | recall@k・MRR・nDCG・事実網羅（LLM なし） | eval-smoke | 題集の閾値（既存の `--gate`） |
| L2 回答 | 引用再現率・精度・事実網羅・誤りの値・回答不能率・検索回数・トークン・p50/p95 | nightly・手動 | 基準との差（下記） |
| L3 忠実度 | 評価者モデルでの裏付け（`--judge`） | 手動・週次 | 記録のみ（評価者の校正が済むまで門にしない） |
| L4 実利用 | 👍👎・回答不能の理由 | 常時 | 👎 を題の候補へ |

### 基準と門（L2）

- 基準: `eval/suites/<題集>/baselines/answer__<モデル>.json`（summary と題ごとの 3 指標）。`--save-baseline` で書く。
- 許容は題集の `golden.yaml` の `answer_gate` に置く:

```yaml
answer_gate:
  floor: { fact_coverage: 0.90, citation_recall: 0.90 }          # 絶対の下限
  max_drop: { fact_coverage: 0.02, citation_recall: 0.03, citation_precision: 0.05 }
  max_rise: { no_answer_rate: 0.03, wrong_facts: 0, p95_ms_ratio: 1.5 }
  max_worse_cases: 3      # 基準で満点だった題が 0 になった数
```

- `--gate` は、下限・低下・上昇・悪化した題の数のどれかを超えたら終了コード 1。超えた項目と題を列挙する。
- モデルの扱い: 既定のモデル（今は `qwen3-8b`）は門。ほかのモデル（`gemma4-12b`・API のモデル）は記録のみ（`--track`）。

### `arag.eval diff <旧.json> <新.json>`

全体の表・タグ別（変わったものだけ）・悪くなった題（指標の前後・回答の先頭・引用と正解の文書）・良くなった題。
`--md` で PR に貼れる形。nightly と `--gate` の出力もこれを使う。

### 再現の情報（結果の `meta`）

`git_sha`・`dirty`・`model_id`・`model`（供給者:名前）・`prompt_sha`（`prompts/*.md` をまとめたハッシュ）・`agent_cfg`・`suite_sha`（golden.yaml のハッシュ）・`started_at`。
あわせて、メッセージの保存（`messages.request`）にも `prompt_sha` を入れる（実利用の回答がどのプロンプトだったかを追える）。

### 題集の運用

- 題は `golden.yaml`、候補は `candidates.yaml`。候補 → 題は PR で（正解の文書・事実・誤りの値を人が確かめる）。
- `arag.eval feedback --since <日付> --out candidates.yaml`: 👎 と回答不能のメッセージを候補として書き出す（質問・回答・引用・理由）。
- 題を足した・直したら基準を更新する（同じ PR）。

## 6. 手元

- `make check` = fast と同じ（lint・型・単体・gen-check・spec-lint）。`make eval-smoke`・`make eval-answer model=<id>`・`make eval-diff a=<旧> b=<新>`・`make spec name=<名前>`。
- `.pre-commit-config.yaml`（pre-commit、MIT）: ruff format/check、eslint（変更ファイル）、gitleaks、commit-msg に `scripts/commit_lint.py`。

## 7. 設計と実装を分ける進め方（`AGENTS.md` に足す）

- 仕様の状態が approved になってから実装する。draft のうちは設計側だけが書く。
- 実装側は `tasks.md` の順に進め、項目ごとにテスト（R 番号を参照）→ 実装 → 印。仕様に無い判断が要るときは、実装を止めて `tasks.md` の「確認事項」に書き、設計側に戻す（勝手に仕様を変えない）。
- 設計側が見るもの: 画面の見た目・文言・動き、プロンプト、評価の結果の解釈、門の許容。実装側に任せるもの: 配線・テスト・CI・定型の移行。
- PR は実装側が起こし、設計側（か人）が仕様との一致と評価の表を見て承認する。

## 8. 決めること（利用者）

1. nightly の実行場所: Mac の自前ランナー（推奨。追加費用なし）か、手動のみか。
2. main の保護を有効にするか（今は直接 push している。有効にすると、すべて PR 経由になる）。
3. 門にするモデル: `qwen3-8b` のままか、026 の再評価のあとで `gemma4-12b` に替えるか。
