/** LLM の接続とモデル目録の画面（specs/013-llm-keys R8）の小さな関数。 */

export const PROVIDERS = ["deepseek", "openai", "anthropic", "google_genai", "openai_compatible"] as const;
export type Provider = (typeof PROVIDERS)[number];

export const PROVIDER_LABEL: Record<Provider, string> = {
  deepseek: "DeepSeek",
  openai: "OpenAI",
  anthropic: "Anthropic",
  google_genai: "Google Gemini",
  openai_compatible: "OpenAI 互換（vLLM など）",
};

/** モデル名の例（入力欄のプレースホルダ）。 */
export const MODEL_EXAMPLE: Record<Provider, string> = {
  deepseek: "deepseek:deepseek-chat",
  openai: "openai:gpt-5-mini",
  anthropic: "anthropic:claude-haiku-5-5",
  google_genai: "google_genai:gemini-3-flash",
  openai_compatible: "openai:qwen3-8b",
};

export const providerLabel = (p: string) => PROVIDER_LABEL[p as Provider] ?? p;

/** 接続の provider から、model に付ける接頭辞。 */
export function modelPrefix(provider: Provider | null | undefined): string | null {
  if (!provider) return null;
  return provider === "openai_compatible" ? "openai" : provider;
}

export type Parsed = { ok: true; value: Record<string, unknown> } | { ok: false; error: string };

export function parseKwargs(text: string): Parsed {
  if (!text.trim()) return { ok: true, value: {} };
  try {
    const v: unknown = JSON.parse(text);
    if (v && typeof v === "object" && !Array.isArray(v)) return { ok: true, value: v as Record<string, unknown> };
    return { ok: false, error: "追加の設定は JSON のオブジェクト（{ … }）で書いてください" };
  } catch {
    return { ok: false, error: "追加の設定が JSON として読めません" };
  }
}

export function moveId(ids: string[], id: string, dir: -1 | 1): string[] {
  const i = ids.indexOf(id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= ids.length) return ids;
  const out = [...ids];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

export const MODEL_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function slugify(model: string): string {
  const name = model.includes(":") ? model.slice(model.indexOf(":") + 1) : model;
  return name
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|-+$/g, "")
    .slice(0, 64);
}

export function validateModelForm(f: {
  id: string;
  label: string;
  model: string;
  provider: Provider | null;
  kwargs: string;
}): string | null {
  if (!MODEL_ID.test(f.id)) return "id は英小文字・数字・-・_ で 64 文字までにしてください";
  if (!f.label.trim()) return "表示名を入力してください";
  if (!f.model.includes(":")) return "モデルは「provider:モデル名」の形で入力してください";
  const prefix = modelPrefix(f.provider);
  if (prefix && f.model.split(":", 1)[0] !== prefix) return `この接続のモデルは「${prefix}:」で始めてください`;
  const k = parseKwargs(f.kwargs);
  return k.ok ? null : k.error;
}

const sameUrl = (a: string, b: string) => a.trim().replace(/\/+$/, "") === b.trim().replace(/\/+$/, "");

/**
 * .env のモデル（base_url つき）を目録に取り込むときの接続。
 * 同じ接続先の「OpenAI 互換」接続があれば使い、無ければ作る（鍵は不要）。base_url が無ければ環境変数のキーのまま。
 */
export function importConnection(
  baseUrl: string | null | undefined,
  credentials: { id: string; provider: string; base_url: string }[],
  modelLabel: string,
): { reuse: string } | { create: { provider: "openai_compatible"; label: string; base_url: string } } | null {
  if (!baseUrl) return null;
  const hit = credentials.find((c) => c.provider === "openai_compatible" && sameUrl(c.base_url, baseUrl));
  if (hit) return { reuse: hit.id };
  return { create: { provider: "openai_compatible", label: `${modelLabel} の接続`.slice(0, 100), base_url: baseUrl } };
}
