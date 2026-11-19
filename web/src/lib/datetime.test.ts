import { expect, test } from "vitest";
import { formatFetchedAt, formatLocalMinute, formatTurnTimestamp, sameLocalDay, dateSeparator } from "@/lib/datetime";

const iso = (y: number, m: number, d: number, h = 0, min = 0) =>
  new Date(y, m - 1, d, h, min).toISOString();

const LABELS = { today: "今日", yesterday: "昨日" };

test("formatTurnTimestamp は時刻のみを返す（日付はセパレータが示す）", () => {
  expect(formatTurnTimestamp(iso(2026, 6, 5, 14, 32))).toBe("14:32");
});

test("formatTurnTimestamp は時分を 2 桁ゼロ埋めする", () => {
  expect(formatTurnTimestamp(iso(2026, 6, 5, 9, 5))).toBe("09:05");
});

test("formatTurnTimestamp は不正値で空文字を返す", () => {
  expect(formatTurnTimestamp("not-a-date")).toBe("");
  expect(formatTurnTimestamp("")).toBe("");
});

test("sameLocalDay は同じ暦日で true", () => {
  expect(sameLocalDay(new Date(2026, 5, 5, 0, 1), new Date(2026, 5, 5, 23, 59))).toBe(true);
  expect(sameLocalDay(new Date(2026, 5, 5, 23, 59), new Date(2026, 5, 6, 0, 1))).toBe(false);
});

test("dateSeparator は今日/昨日を相対表記にする", () => {
  const now = new Date(2026, 5, 5, 10, 0);
  expect(dateSeparator(iso(2026, 6, 5, 8, 0), now, LABELS)).toBe("今日");
  expect(dateSeparator(iso(2026, 6, 4, 8, 0), now, LABELS)).toBe("昨日");
});

test("dateSeparator は同年の他日付を月日で返す", () => {
  const now = new Date(2026, 5, 5, 10, 0);
  expect(dateSeparator(iso(2026, 6, 1, 8, 0), now, LABELS)).toBe("6月1日");
});

test("dateSeparator は別年なら年を含める", () => {
  const now = new Date(2026, 5, 5, 10, 0);
  expect(dateSeparator(iso(2025, 6, 5, 8, 0), now, LABELS)).toBe("2025年6月5日");
});

test("dateSeparator は不正値で空文字を返す", () => {
  expect(dateSeparator("nope", new Date(), LABELS)).toBe("");
});

test("formatFetchedAt: システムの時刻を日付と分まで、時差で直さずに出す", () => {
  {
    expect(formatFetchedAt("2026-11-18T20:19+09:00")).toBe("2026-11-18 20:19");
    expect(formatFetchedAt("2026-11-18T09:05:33")).toBe("2026-11-18 09:05");
    expect(formatFetchedAt("不明")).toBe("不明");
  }
});

test("formatLocalMinute: 端末の時刻で分まで", () => {
  expect(formatLocalMinute(new Date(2026, 10, 19, 20, 14, 30).toISOString())).toBe("2026-11-19 20:14");
  expect(formatLocalMinute("x")).toBe("");
});
