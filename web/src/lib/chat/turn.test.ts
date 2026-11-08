import { describe, expect, it } from "vitest";
import { applyEvent, isTerminal, newTurn, toToolCall, turnFromMessage, type ApiStep, type RunEvent } from "./turn";

const step = (over: Partial<ApiStep>): ApiStep => ({
  id: "c1",
  name: "search",
  label: "資料を検索",
  status: "running",
  duration_ms: 0,
  input: { query: "MX-17" },
  output: null,
  parent_id: null,
  summary: "検索しています",
  ...over,
});

const source = {
  id: "d1",
  title: "規程.pdf",
  score: 0.8,
  sections: [{ id: "x1", n: 1, heading: "3 章", body: "即時停止", block_type: "text", page: 4 }],
};

function play(events: RunEvent[]) {
  return events.reduce(applyEvent, newTurn("MX-17 は？"));
}

describe("applyEvent", () => {
  it("ストリームを Turn に写す", () => {
    const t = play([
      { type: "run.started", run_id: "r1", thread_id: "t1", message_id: "m1", model_id: "qwen" },
      { type: "step", step: step({}) },
      { type: "step", step: step({ id: "c1:search", name: "retrieve", parent_id: "c1", input: { query: "MX-17", mode: "hybrid" } }) },
      { type: "step", step: step({ status: "done", duration_ms: 120, summary: "資料 1 件" }) },
      { type: "sources", sources: [source], citation_map: { "1": { source_id: "d1", section_id: "x1" } } },
      { type: "answer.delta", text: "停止" },
      { type: "answer.delta", text: "する[1]" },
    ]);
    expect(t.runId).toBe("r1");
    expect(t.messageId).toBe("m1");
    expect(t.steps.map((s) => [s.id, s.name, s.status])).toEqual([
      ["c1", "retrieve", "done"],
      ["c1:search", "vector_search", "running"],
    ]);
    expect(t.steps[0].durationMs).toBe(120);
    expect(t.answer).toBe("停止する[1]");
    expect(t.citationMap).toEqual({ 1: { sourceId: "d1", sectionId: "x1" } });
    expect(t.sources[0].sections[0]).toMatchObject({ heading: "3 章", page: 4, blockType: "text" });
    expect(t.streaming).toBe(true);
  });

  it("完了で本文・トークン・時間を確定し、残ったステップを閉じる", () => {
    const t = play([
      { type: "step", step: step({}) },
      { type: "answer.delta", text: "途中" },
      {
        type: "run.completed",
        message_id: "m1",
        answer: "最終の回答[1]",
        tokens_in: 100,
        tokens_out: 20,
        duration_ms: 1500,
        no_answer_reason: null,
        citation_map: { "1": { source_id: "d1", section_id: "x1" } },
        sources: [source],
      },
    ]);
    expect(t).toMatchObject({ answer: "最終の回答[1]", tokens: 120, durationMs: 1500, status: "done", streaming: false });
    expect(t.steps[0].status).toBe("error");
  });

  it("書き直しで本文を空にする", () => {
    const t = play([
      { type: "answer.delta", text: "古い" },
      { type: "answer.reset" },
      { type: "answer.delta", text: "新しい" },
    ]);
    expect(t.answer).toBe("新しい");
  });

  it("失敗・取消を状態にする", () => {
    expect(play([{ type: "run.failed", code: "generation_failed", message: "失敗しました" }])).toMatchObject({
      status: "error",
      error: "失敗しました",
      streaming: false,
    });
    expect(play([{ type: "run.cancelled", message_id: "m1" }]).status).toBe("cancelled");
    expect(isTerminal({ type: "run.cancelled", message_id: "m1" })).toBe(true);
    expect(isTerminal({ type: "answer.reset" })).toBe(false);
  });

  it("同じステップを何度当てても 1 つ", () => {
    const ev: RunEvent = { type: "step", step: step({}) };
    expect(play([ev, ev, ev]).steps).toHaveLength(1);
  });
});

describe("toToolCall", () => {
  it("文書ツールは fetch_document、キーワードは語を query にする", () => {
    expect(toToolCall(step({ name: "read_section", input: { section: "[2]" } }))).toMatchObject({
      name: "fetch_document",
      input: { document: "[2]" },
    });
    expect(toToolCall(step({ name: "keyword_search", input: { terms: ["MX-17", "部品"] } })).input.query).toBe("MX-17 部品");
    expect(toToolCall(step({ name: "retrieve", input: { mode: "keyword" } })).name).toBe("bm25_search");
  });
});

describe("turnFromMessage", () => {
  it("保存済みメッセージを Turn にする", () => {
    const t = turnFromMessage({
      id: "m1",
      ordinal: 1,
      query: "質問",
      answer: "回答[1]",
      status: "completed",
      model_id: "qwen",
      tokens_in: 10,
      tokens_out: 5,
      duration_ms: 900,
      steps: [step({ status: "done" })],
      sources: [source],
      citation_map: { "1": { source_id: "d1", section_id: "x1" } },
      no_answer_reason: null,
      created_at: "2026-11-09T00:00:00Z",
      feedback: { rating: "down", reason_tags: ["wrong"], comment: null },
    });
    expect(t).toMatchObject({ status: "done", tokens: 15, messageId: "m1", streaming: false });
    expect(t.feedback).toEqual({ rating: "down", reasonTags: ["wrong"], comment: null });
    expect(t.citationMap[1].sectionId).toBe("x1");
  });
});
