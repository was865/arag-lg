# 031 — 設計

## ツール（`agent/ops.py`・`agent/tools.py`）

- `format_outline(filename, secs, start, head=120, tail=60)`（純関数）。節が `head + tail` を超えれば先頭と末尾、間に `…（中略: 第 a〜b 節は未表示。読むには get_outline に start=a を渡す…）`。`start` があれば `OUTLINE_MAX`（200）節。目次の節は `_is_toc`（NFKC・空白を除いて「目次」「contents」など）で探し、先頭に案内を出す。
- 省略の印は `OUTLINE_OMITTED`・`DOC_OMITTED`（`OMITTED_MARKS`）。確認はこれで省略を見つける。
- 同じ呼び出しの省略は `StepMiddleware`。`RunContext.tool_seen`（名前＋引数の JSON）。ターンの始め（`read_image`）で空にする。`ask_user` は対象外。
- `ask_user(question, options)` は `return_direct=True`。呼ぶと調査の輪が終わる。

## 文書名で読む（`find_named_documents`・`primer._read_named`）

- 名前の照合: `lower(regexp_replace(normalize(filename, NFKC), '\s+', '', 'g'))` が質問（同じ正規化）に含まれるか、拡張子を除いた名前が 8 文字以上で含まれるか。Python の `filename_in_question` で同じ判定を確かめる。従来の語の切り出し（`named_document_refs`）も残す。
- 長い文書: `op_get_outline(head=20, tail=20)` を `<章立て>…</章立て>` で添え、目次の節の ID（`TOC_SECTION_ID`）があれば `op_read_section` で本文を足す（引用できる）。どちらも「指定の文書を読む」の子のステップとして記録する。

## 確認（`flow.review`・`middleware`）

- 種類と順: `omitted` → `gap` → `table` → `numbers`（`pick_review`、同期）→ `reason`（`reason_review`、補助モデル）。どれも 1 ターンに 1 度。
- `omitted`: `OMITTED_GAP`（`GAP` に「表示されていません」「省略されて」を足したもの）に当たり、ターンのツールの結果か `ctx.primer.text` に省略の印があるとき。
- `GAP` に「特定できません」「お答えすることができません」を足した。
- `reason`: `reason_check.py`。`WHY` に当たる質問で、下書きの引用の資料を渡して JSON（`subject`・`subject_in_material`・`reason_linked`・`why`）を得る。両方 true で裏付けあり。読めなければ判定なし（差し戻さない）。プロンプトは `prompts/reason_check.md`。
- 注記: `reason` を済ませた後の通過のときに `reason_caveat` で書き直しを確かめ、裏付けが無ければ状態の `caveat` に置く。`finalize` が回答の末尾に足し、`reason_caveat` のステップを記録する。

## 聞き返し（`flow`・`runner`・web）

- `guard`: 最後が `ask_user` の ToolMessage なら `guard="clarify"`・`outcome="clarify"`。辺は「下書きへの退避」と同じ `use_draft`（確認を通さず確定へ。札は「下書き・聞き返し」。LangGraph の図は同じ 2 節点の間の辺を 1 本にまとめるため）。
- `finalize._finish_clarify`: 問いを `AIMessage(additional_kwargs={"clarify": True, "options": …})` として状態に足し、`Completion(suggestions=options, followups=False)`。`system/clarify` のステップを記録。
- runner: `Completion.suggestions` をメッセージの `suggestions` に保存し、`run.completed` で送る。
- `AgentPolicyMiddleware`: `no_ask_reason`（雑談・書き直し・前のターンが聞き返し）なら `ask_user` をツールから外す。前のターンが聞き返しのときは `system/ask_user_blocked` を記録。
- web: `isClarify(turn)`（`ask_user` のステップがある）なら候補の見出しを `clarifyTitle` にする。`ask_user` の入力は `SystemFields` で問いと選択肢を出す。流れの推定では `system/clarify` を確定の節点に置き、`use_draft` の辺を通ったとみなす。

## 確かめ方

- 偽モデルのテスト（`test_agent_graph.py`・`test_agent_ops.py`）。
- 3100 で実際に: 上の 2 つの質問。harukaze_mix 69 題（`eval/.reports/hm-gemma4-12b-031`）。
