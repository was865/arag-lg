# 016 推論の構成を部品ごとに選べるようにする — 要件

推論の各役割を「自前（GPU 機・CPU コンテナ）」か「外部 API」かで、起動時の設定だけで選べるようにする。
オフライン運用（データを外に出さない）と、GPU 機なしの軽量運用（API だけで動かし、起動するサービスを減らす）の両方を満たす。

| 役割 | 自前 | 外部 API |
|---|---|---|
| 解析 | docling-serve（GPU / CPU） | —（CPU 版で足りるため対象外） |
| 埋め込み | TEI | OpenAI 互換 `/embeddings`（OpenAI・Jina・Voyage など。vLLM・Infinity も同じ形） |
| 並べ替え（rerank） | TEI | Cohere 互換 `/rerank`（Cohere・Jina・Voyage など。vLLM も同じ形）、または使わない |
| 文脈の付与 | vLLM（OpenAI 互換） | `provider:model` |
| 図の説明 | vLLM（Qwen2.5-VL など） | `provider:model` |
| 会話 | モデル目録（013、画面で管理） | 同左 |

- R1 **埋め込み。** `ARAG_EMBED_PROVIDER=tei|openai`。URL は `ARAG_EMBED_URL`（未設定なら従来の `ARAG_TEI_EMBED_URL`）、鍵は `ARAG_EMBED_API_KEY`、次元を指定できる API 向けに `ARAG_EMBED_DIMENSIONS`。検索側と入庫側は同じ設定から作る。
- R2 **並べ替え。** `ARAG_RERANK_PROVIDER=tei|cohere`。URL は `ARAG_RERANK_URL`（未設定なら `ARAG_TEI_RERANK_URL`）、鍵は `ARAG_RERANK_API_KEY`。応答の `results` と `data` のどちらにも対応し、元の順に戻す。URL が無ければ従来どおり並べ替えなしで動く。
- R3 **図の説明。** 文脈の付与と同じく `ARAG_VLM_BASE_URL`・`ARAG_VLM_MODEL_KWARGS` で自前の OpenAI 互換サーバを指せる。
- R4 **起動時の選択。** 代表的な組み合わせ（オフライン・軽量・混在）を `.env` の例として用意し、GPU 機の compose は役割ごとに profile で起動を選べる（図の説明用 vLLM を追加）。
- R5 **見える化と安全。** 起動時に各役割の構成（自前か API か・モデル名）を 1 行のログに出す。鍵はログ・readiness に出さない。readiness は自前のサービスだけを確かめ、外部 API は `external` と表示する。
- R6 **埋め込みの切り替え。** 埋め込みのモデルや次元を変えるときは別のコレクション（`ARAG_QDRANT_COLLECTION`）にして再索引する。次元が合わないときは今と同じく入庫を止めて理由を出す。
