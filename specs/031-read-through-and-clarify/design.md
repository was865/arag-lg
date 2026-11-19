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

### 聞き返しの見せ方と候補（T13、2026-11-19）

- 聞き返しで終えたターンは引用が無いのが当然なので、検索の過程の見出しを「引用なし」（注意の色）にせず「聞き返した」とする（`searchStory().clarify`）。
- 「この資料」の候補で最近の文書を先に置くのは、内容の語が無い質問（要点・まとめなど）だけにする。「この資料の締付トルクは？」のように内容の語があれば検索の順が当てになるので、最近の文書は検索でも関連の高いものだけを先に置く（`has_content_terms`）。関係の無い文書（学習ハンドブックなど）を候補にしない。

### 聞き返しの評価と広げ方（T12・T14、2026-11-19）

- 評価: `eval/suites/harukaze_clarify`（資料と KB は harukaze_mix）。聞き返すべき題 9・答えるべき題 9。題の `expect_clarify` と、結果の `clarified`（ask_user かシステムの聞き返し）から「聞き返し率」「聞き返すべき題で聞き返した」「聞き返す必要の無い題で聞き返した」を出す。聞き返すべき題は、聞き返せば事実網羅 1.0。
- 広げる前（Gemma 4 12B）: 聞き返すべき題 3/9、必要の無い題 0/9。モデルの ask_user は 0 回。添付・この表・「この件」「それは」は検索して当て推量で答え、「その文書」は関連の高い文書が 1 つで選択肢が 2 つに満たず聞き返さなかった。
- 広げた後: 8/9、0/9。harukaze_mix（69 題）は引用・網羅とも前と同じで、聞き返しは 0 件。
- 残り: hc09「価格はいくらですか？」（モデルの判断）は、主な価格を並べて答える。両方（全部）を短く答えられるなら答える、という R6 に沿っているとも言える。モデルの判断の聞き返しを増やすのは、プロンプトを緩めると答えるべき題で聞き返し出すので、題を増やしてから考える。

### 長い文書の構成を続けて尋ねる（T15〜T18、2026-11-19）

実際の失敗（学習ハンドブック 643 節）: 1 ターン目は文書名があり章立てと目次の節を添えたが、モデルは付録だけを「最後の章」と答えた。2 ターン目からは文書名が無く、普通の検索だけになり、検索は目次の節（見出し「目 次」、本文は表）を上げなかった。モデルはツールを呼ばずに、検索で拾った見出しと「分野」から章立てを作った（第2・3・5章の見出しは資料に無い）。確認は数字（第1章の「1」など）を照合して通した。解析でも章の扉の多くが見出しになっていない（第1・4章だけ）。

- T15: 構成の質問で、前のターンで引用した文書が 1 つなら章立てと目次の節を添える（`_read_structure`）。
- T16: 注意は検索結果（データとして隔離する部分）の中でなく外に添える（`Primer.note`）。最初は検索結果の中に「最後の章は両方を答える」を入れたところ、「目次を教えて」にも最後の章を答えた（handbook_structure の hs02 が 1.00 → 0.29）。注意は問われたことに合わせて分ける。
- T17: 「第N章: 見出し」の見出しを資料と突き合わせる（NFKC・空白と記号を除き、先頭 10 文字）。
- T18: handbook_structure（作った docx。章の扉は見出しの書式にしない・模擬試験の見出しに「第N章」）。前: hs01 が 2 回とも 0.50（付録だけ）、続けての 4 題は 1.00（この文書の大きさでは検索が目次を上げる）。後: 5 題とも 2 回 1.00。harukaze_mix 69 題・harukaze_clarify は変わらず。実際の文書でも 3100 で同じ 3 ターンを確かめ、最後の章（第5章と付録）・目次とも正しくなった。
- 残り: 解析で章の扉が見出しにならない問題（Docling）は別に扱う。

### PDF の章を柱から決める（T19・T20、2026-11-19）

学習ハンドブック（318 ページ・691 見出し）の docling.json を調べた結果:

- docling は PDF の見出しをすべて同じ深さ（level 1）にする。章と節を見出しの深さでは分けられない。
- 章の扉の小さな札「第 N 章」は、第1・4章では見出し、第2・3・5章では本文になった。本文になった札は前の節の本文の末尾に混ざり、章の題は他の 690 の見出しと同じ深さの見出しになった（「第2章が無い」のではなく、章と分からなかった）。
- 各ページの柱（page_header）には「第2章 エンタープライズ統合と本番運用」のように章が正しく出ていたが、2 ページ以上に出るヘッダは社名などの飾りとして外していた（`keep_unique_page_headers`）。
- 見出しの末尾にカードの番号が混ざる（「POC から本番運用へ。 2」）。

決め方（`running_chapters`）: 2 ページ以上に出る柱を候補にし、ほかの候補と範囲が重なるもの（本の題名・図の文字の取り違え「層」など）を重なりの多いものから外す。2 つ以上残れば章とし、始まりは前の章の柱の後で章の名前と同じ見出しのあるページ（扉）。柱の無い章末のまとめのページも、次の扉より前なので前の章に入る。手元の PDF・Word 20 件のうち章が決まったのはこの 1 件だけで、ほかの分割は変わらない（再索引は `--content-hash` でこの文書だけにした）。

確かめたこと（3100、目次の節に頼らない問い）: 「第3章では何を学びますか」は章の題と内容とも正しい。「第2章の最後の節」は、章の節を添える前は第2章の途中の節（POC から本番運用へ）を答えた。添えた後は「A/B テストとオブザーバビリティ。」（ページ順の最後）か「2.8 まとめ」（番号の最後）と、どちらも資料どおり。評価は handbook_structure・harukaze_mix とも前と同じ（hm21・hs03 の揺れは変更前のコードでも 3 回に 1 回出る）。

