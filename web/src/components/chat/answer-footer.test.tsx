import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AnswerFooter, formatTokens } from "@/components/chat/answer-footer";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";

function render() {
  return renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      <AnswerFooter
        tokens={1234}
        durationMs={4200}
        onCopy={() => {}}
        onDownload={() => {}}
        onDownloadHtml={() => {}}
        onRegenerate={() => {}}
        onFeedback={() => {}}
        onFeedbackDetail={() => {}}
        feedback={null}
      />
    </LocaleProvider>,
  );
}

describe("AnswerFooter（specs/028 R8・R9）", () => {
  it("常に見せる操作はコピー・再生成・良い・良くない・その他の 5 つ", () => {
    const html = render();
    const labels = [...html.matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1]);
    expect(labels).toEqual([ja.chat.copyTitle, ja.chat.regenerateTitle, ja.chat.feedbackUpTitle, ja.chat.feedbackDownTitle, ja.chat.moreActions]);
  });

  it("出典の札・保存のボタン・info のボタンは出さない", () => {
    const html = render();
    expect(html).not.toContain("出典");
    expect(html).not.toContain(ja.chat.saveMarkdown);
    expect(html).not.toContain("この回答の詳細");
  });
});

describe("formatTokens", () => {
  it("1000 以上は k で縮める", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(1234)).toBe("1.2k");
    expect(formatTokens(2000)).toBe("2k");
  });
});
