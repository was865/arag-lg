import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("文字の段階と色を別物として残す", () => {
    expect(cn("text-body text-accent", "text-danger")).toBe("text-body text-danger");
  });
  it("文字の段階どうしは後勝ち", () => {
    expect(cn("text-footnote", "text-body")).toBe("text-body");
  });
  it("角丸の段階どうしは後勝ち", () => {
    expect(cn("rounded-control", "rounded-full")).toBe("rounded-full");
  });
});
