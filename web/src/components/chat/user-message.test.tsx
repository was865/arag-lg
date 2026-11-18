import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { UserMessage } from "@/components/chat/messages";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";

const render = (node: React.ReactNode) =>
  renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      {node}
    </LocaleProvider>,
  );

const labels = (html: string) => [...html.matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1]);

describe("質問の吹き出しと下の操作（specs/005 R34）", () => {
  it("吹き出しの下に時刻・コピー・編集を並べる", () => {
    const html = render(<UserMessage text="q" sentAt="2026-11-19T01:16:00" onEdit={() => {}} />);
    expect(html).toContain(">01:16</time>");
    expect(labels(html)).toEqual([
      ja.chat.sentAt.replace("{time}", "01:16"),
      ja.chat.copyQuestion,
      ja.chat.editQuestion,
    ]);
  });

  it("編集できないとき（生成中・未保存）はコピーだけを出す", () => {
    const html = render(<UserMessage text="q" />);
    expect(labels(html)).toEqual([ja.chat.copyQuestion]);
    expect(html).not.toContain("<time");
  });
});
