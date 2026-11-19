"use client";

/** 会話のモデルの一覧と選択（この端末に覚える）。画像を添えられるか（図の説明用モデルの有無）も返す。 */
import { useEffect, useState } from "react";
import { useToast } from "@/components/feedback/toast-provider";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { chatApi } from "@/lib/chat/api";
import { MODEL_STORAGE_KEY } from "@/lib/constants";
import type { ModelOption } from "@/lib/types";

const LOADING_MODEL: ModelOption = { id: "", label: "読み込み中…", tag: "", desc: "", available: false };
const NO_MODEL: ModelOption = { id: "", label: "モデル未設定", tag: "", desc: "", available: false };

export function useModels() {
  const { t } = useT();
  const push = useToast();
  const [models, setModels] = useState<ModelOption[] | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [imageInput, setImageInput] = useState(false);

  useEffect(() => {
    chatApi
      .models()
      .then((m) => {
        const opts = m.models.map((x) => ({
          id: x.id,
          label: x.label,
          tag: x.tags[0] ?? "",
          desc: x.tags.join(" · "),
          available: x.available,
        }));
        setModels(opts);
        setImageInput(Boolean(m.image_input));
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(MODEL_STORAGE_KEY);
        } catch {}
        const usable = opts.find((o) => o.id === saved && o.available);
        setModelId(usable?.id ?? m.default_id ?? null);
      })
      .catch(() => {
        setModels([]);
        push("モデルの一覧を取得できませんでした", "error");
      });
  }, [push]);

  const model = models === null ? LOADING_MODEL : (models.find((m) => m.id === modelId) ?? models[0] ?? NO_MODEL);

  const selectModel = (m: ModelOption) => {
    setModelId(m.id);
    try {
      localStorage.setItem(MODEL_STORAGE_KEY, m.id);
    } catch {}
    push(interpolate(t.feedback.modelSwitched, { label: m.label }), "success");
  };

  // 一覧が届く前は model_id が決まっていない。そのまま送るとサーバーの既定（目録の先頭）で答えてしまい、
  // 画面に見えているモデルと食い違うので、届くまで送信を止める
  return { models: models ?? [], model, modelId, modelLoading: models === null, imageInput, selectModel };
}
