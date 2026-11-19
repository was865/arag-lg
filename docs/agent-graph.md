# 回答の流れ（生成物）

`make graph` が `api/src/arag/agent/flow.py` のグラフの定義から書き出す。手で直さない
（CI の `graph-check` が一致を確かめる）。仕様は `specs/029-explicit-graph/`。
「調査」の中は create_agent（モデル ⇄ ツールの輪）。

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	read_image(画像)
	understand(理解)
	primer_search(最初の検索)
	guard(見張り)
	review(確認)
	finalize(確定)
	followups(続けて聞く)
	__end__([<p>__end__</p>]):::last
	__start__ --> read_image;
	finalize -. &nbsp;なし&nbsp; .-> __end__;
	finalize -. &nbsp;候補あり&nbsp; .-> followups;
	guard -. &nbsp;下書き・聞き返し&nbsp; .-> finalize;
	guard -. &nbsp;やり直し&nbsp; .-> investigate\3a__start__;
	guard -. &nbsp;通過&nbsp; .-> review;
	investigate\3a__end__ --> guard;
	primer_search -. &nbsp;聞き返し&nbsp; .-> finalize;
	primer_search -. &nbsp;調査へ&nbsp; .-> investigate\3a__start__;
	read_image --> understand;
	review -. &nbsp;通過&nbsp; .-> finalize;
	review -. &nbsp;差し戻し&nbsp; .-> investigate\3a__start__;
	understand -. &nbsp;雑談&nbsp; .-> investigate\3a__start__;
	understand -. &nbsp;資料&nbsp; .-> primer_search;
	followups --> __end__;
	subgraph investigate
	investigate\3a__start__(<p>__start__</p>)
	investigate\3amodel(モデル)
	investigate\3atools(ツール<hr/><small><em>__tools = search, keyword_search, list_documents, get_outline, read_section, read_document, table_query, calculate, ask_user</em></small>)
	investigate\3aRecordedSummarization\2ebefore_model(会話の要約)
	investigate\3a__end__(<p>__end__</p>)
	investigate\3aRecordedSummarization\2ebefore_model --> investigate\3amodel;
	investigate\3a__start__ --> investigate\3aRecordedSummarization\2ebefore_model;
	investigate\3amodel -.-> investigate\3aRecordedSummarization\2ebefore_model;
	investigate\3amodel -.-> investigate\3a__end__;
	investigate\3amodel -.-> investigate\3atools;
	investigate\3atools -.-> investigate\3aRecordedSummarization\2ebefore_model;
	investigate\3atools -.-> investigate\3a__end__;
	end
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

| 節点 | 表示名 | 役目 |
|---|---|---|
| `read_image` | 画像 | 添付画像を文章にして質問に添える（画像が無ければ素通り） |
| `understand` | 理解 | 質問の種類・検索語・表の集計の要否を整理する（初回は質問文での検索と並行） |
| `primer_search` | 最初の検索 | 整理した検索語で検索し、結果を質問に添える用意をする |
| `investigate` | 調査 | モデルとツールの輪（create_agent。要約・モデルの切り替え・回数の上限を含む） |
| `guard` | 見張り | 空の生成のやり直し・差し戻しへの返事や引用の消えた書き直しの取り消し |
| `review` | 確認 | 調べ残し・表の集計・数字を確かめ、当てはまれば差し戻す（種類ごとに 1 度） |
| `finalize` | 確定 | 数字の照合・引用の整形と刈り込み・回答の分類をして、完了を送る |
| `followups` | 続けて聞く | 完了の後に、続けて聞く質問の候補を作って届ける |

辺の札: `chat` = 雑談・`docs` = 資料・`retry` = やり直し・`use_draft` = 下書き・聞き返し・`investigate` = 調査へ・`clarify` = 聞き返し・`ok` = 通過・`send_back` = 差し戻し・`pass` = 通過・`followups` = 候補あり・`end` = なし
