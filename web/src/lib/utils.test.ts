import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("文字の段階と色を別物として残す", () => {
    expect(cn("text-body text-accent", "text-danger")).toBe("text-body text-danger");
  });
  it("文字の段階どうしは後勝ち", () => {
    expect(cn("text-footnote", "text-body")).toBe("text-body");
  });
  it("mini・display も文字の段階として扱う", () => {
    expect(cn("text-mini text-muted", "text-accent")).toBe("text-mini text-accent");
    expect(cn("text-caption", "text-display")).toBe("text-display");
    expect(cn("text-display", "text-hero")).toBe("text-hero");
  });
  it("角丸の段階どうしは後勝ち", () => {
    expect(cn("rounded-control", "rounded-full")).toBe("rounded-full");
  });
});
