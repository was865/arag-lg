# 018 評価用資料の拡充 — 設計

## 資料（R1・R2）

- 架空の会社「株式会社ハルカゼ精工」（ポンプ製造）を舞台にする。拠点は浜松第二工場とペナン工場。
  主な製品は HP-300・HP-320、部品は SK-300 などとし、資料どうしで型番・人名・日付が食い違わないようにする。
  英語資料に出てくる仕入先 Aster Seals Ltd. も架空の会社。
- 生成スクリプトは `eval/assets/harukaze_mix/build.py`。内容はスクリプトに直接書く（LLM は使わない）。
  出来上がった資料は `eval/assets/harukaze_mix/docs/` に置き、git に入れる。
  - Word: python-docx（MIT）
  - Excel: openpyxl（MIT）。数式は値が入らないため、合計などは数値で書く
  - PowerPoint: python-pptx（MIT）。棒グラフを 1 枚入れる
  - 文字のある PDF: reportlab（BSD）の CID フォント HeiseiKakuGo-W5。フォントは埋め込まない
  - 走査 PDF: Pillow で A4・150dpi の画像を描き、汚れ・わずかな傾き・ぼかし・赤い印影を加えて、画像だけの PDF にする。
    日本語フォントの既定は macOS の Hiragino Sans GB とし、`ARAG_ASSET_FONT` で替えられるようにする
- これらのライブラリは `api/pyproject.toml` の依存グループ `assets` に入れ、本体の依存には入れない。

## 題（R3）

- `eval/suites/harukaze_mix/golden.yaml`。種類は `tags` で分ける。
  言語は `ja` / `en` / `cross`、種類は `docx` / `xlsx` / `pptx` / `pdf` / `scan` / `en-doc` / `table` / `version` / `similar` / `multi` / `noans` / `multiturn`。
- 新旧の版の題は、改訂版の値（例: 52 N·m）を問う題と、旧版の値（45 N·m）を明示して問う題を両方置く。
- key_facts は、言い換えや英語で答えても当たる語を並べる。日付は `canon()` が揃えるので、日本語の表記だけを書く。

## 続けて尋ねる題（R4）

- `Case.turns: list[str]`（既定は空）。前の質問を順に並べる。
- 回答評価（`run_case`）は、`turns` を同じスレッドで順に尋ねてから `query` を尋ね、`query` の回答だけを採点する。
  - 最初の質問は `POST /v1/runs`、続きは `POST /v1/threads/{thread_id}/runs`。
  - `RunApi.start(body, thread_id=None)` は `(run_id, thread_id)` を返す。
  - 前の質問が完了しなかったら、その題は失敗（`前の質問 n が終わりませんでした`）とする。
- 検索評価は今までどおり `rewritten`（なければ `query`）で測る。続けて尋ねる題には `rewritten` を必ず書く。

## 確定と記録（R5・R6）

- 候補の段階では閾値を置かない。利用者の確認が終わったら、検索評価の基準値を `--save-baseline` で保存する。
- 結果は `specs/018-eval-corpus-mix/report.md` に記録する。形式（tag）ごとに事実網羅率を分けて示す。
