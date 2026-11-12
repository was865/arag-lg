# 027 タスク

設計: 済（このディレクトリ）。実装は Opus に任せる。各項目はテストを先に書く。

## 第 1 歩: 評価の門（いちばん効く。GitHub の設定は要らない）

- [ ] T1 `arag.eval diff`（全体・タグ別・悪化／改善の題、`--md`）— R16
- [ ] T2 結果に `meta`（git_sha・model・prompt_sha・agent_cfg・suite_sha）— R17
- [ ] T3 `answer --save-baseline` / `--gate` / `--track` と `answer_gate` の読み取り — R15・R18
- [ ] T4 harukaze_mix の `answer_gate` と、`qwen3-8b` の基準を置く（026 の再評価のあと）— R18
- [ ] T5 `make check`・`make eval-smoke`・`make eval-answer`・`make eval-diff` — R20

## 第 2 歩: 仕様の道具

- [ ] T6 `scripts/spec_lint.py` と `specs/.speclint.toml`（古い仕様は legacy）、テスト — R2・R3・R4
- [ ] T7 `specs/_template/` と `make spec` — R1
- [ ] T8 `docs/adr/` と最初の 3 件（系統が導くエージェント / 会話モデルの選定 / 評価の門）— R5
- [ ] T9 026・027 の `requirements.md` に状態を書き、026 のテストに R 番号の参照を足す — R2・R4

## 第 3 歩: CI

- [ ] T10 `ci.yml` を fast / integration に分け、spec-lint・commit-lint・gitleaks を足す — R8・R9・R10・R11
- [ ] T11 `eval-smoke.yml` — R12
- [ ] T12 PR の雛形、Dependabot、`audit.yml` — R7・R14
- [ ] T13 `.pre-commit-config.yaml` — R21
- [ ] T14 `AGENTS.md` に進め方（設計 §7）を足し、`docs/operations.md` に評価と CI の節を足す — R22

## 第 4 歩: 夜間の評価（利用者の判断のあと）

- [ ] T15 自前ランナーの手順（`docs/operations.md`）と `nightly-eval.yml` — R13
- [ ] T16 `arag.eval feedback` — R19
- [ ] T17 main の保護（必須の検査）— R6

## 確認事項

- 設計 §8 の 3 点（実行場所・main の保護・門にするモデル）。
