import { describe, expect, it } from "vitest";
import { importConnection, modelPrefix, moveId, parseKwargs, PROVIDER_LABEL, slugify, validateModelForm } from "./llm";

describe("LLM 管理の小さな関数", () => {
  it("provider の表示名と model の接頭辞", () => {
    expect(PROVIDER_LABEL.openai_compatible).toBe("OpenAI 互換（vLLM など）");
    expect(modelPrefix("openai_compatible")).toBe("openai");
    expect(modelPrefix("deepseek")).toBe("deepseek");
    expect(modelPrefix(null)).toBeNull();
  });

  it("parseKwargs は空なら {}、オブジェクト以外は誤り", () => {
    expect(parseKwargs("")).toEqual({ ok: true, value: {} });
    expect(parseKwargs(' {"temperature": 0.2} ')).toEqual({ ok: true, value: { temperature: 0.2 } });
    expect(parseKwargs("[1]").ok).toBe(false);
    expect(parseKwargs("{bad").ok).toBe(false);
  });

  it("moveId は上下に 1 つ動かし、端では変えない", () => {
    expect(moveId(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
    expect(moveId(["a", "b", "c"], "b", 1)).toEqual(["a", "c", "b"]);
    expect(moveId(["a", "b"], "a", -1)).toEqual(["a", "b"]);
    expect(moveId(["a", "b"], "x", 1)).toEqual(["a", "b"]);
  });

  it("slugify は id の候補を作る", () => {
    expect(slugify("deepseek:deepseek-chat")).toBe("deepseek-chat");
    expect(slugify("openai:Qwen3 8B")).toBe("qwen3-8b");
    expect(slugify("")).toBe("");
  });

  it("validateModelForm は id・接頭辞・JSON を確かめる", () => {
    const base = { id: "ds", label: "DeepSeek", model: "deepseek:deepseek-chat", provider: "deepseek" as const, kwargs: "" };
    expect(validateModelForm(base)).toBeNull();
    expect(validateModelForm({ ...base, id: "Bad Id" })).toMatch(/id/);
    expect(validateModelForm({ ...base, label: " " })).toMatch(/表示名/);
    expect(validateModelForm({ ...base, model: "deepseek-chat" })).toMatch(/provider:/);
    expect(validateModelForm({ ...base, model: "openai:gpt" })).toMatch(/deepseek:/);
    expect(validateModelForm({ ...base, provider: null, model: "openai:gpt" })).toBeNull();
    expect(validateModelForm({ ...base, kwargs: "[" })).toMatch(/JSON/);
  });
});

describe("importConnection", () => {
  const creds = [
    { id: "a", provider: "deepseek", base_url: "" },
    { id: "b", provider: "openai_compatible", base_url: "http://gpu:8090/v1/" },
  ];
  it("同じ接続先の OpenAI 互換接続を使い、無ければ作る", () => {
    expect(importConnection("http://gpu:8090/v1", creds, "Qwen")).toEqual({ reuse: "b" });
    expect(importConnection("http://gpu:8091/v1", creds, "Qwen VL")).toEqual({
      create: { provider: "openai_compatible", label: "Qwen VL の接続", base_url: "http://gpu:8091/v1" },
    });
    expect(importConnection(null, creds, "DeepSeek")).toBeNull();
  });
});
