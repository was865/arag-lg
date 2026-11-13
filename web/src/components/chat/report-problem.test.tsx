import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CancelledNotice, ErrorNotice, ReportProblem, canReport } from "@/components/chat/answer-footer";
import { FeedbackForm } from "@/components/chat/feedback-popover";
import { Popover } from "@/components/ui/popover";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";
import { applyEvent, newTurn } from "@/lib/chat/turn";

const render = (node: React.ReactNode) =>
  renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      {node}
    </LocaleProvider>,
  );

describe("問題を報告（specs/028 R11・R12）", () => {
  it("報告の欄に、管理者に共有されることを書き、理由に「エラー・回答が出ない」がある", () => {
    const html = render(
      <Popover>
        <FeedbackForm initial={{ reasonTags: ["error"], comment: null }} onSubmit={() => {}} />
      </Popover>,
    );
    expect(html).toContain(ja.chat.feedbackShareNote);
    expect(html).toMatch(/aria-pressed="true"[^>]*>エラー・回答が出ない/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>事実誤り/);
  });

  it("失敗・取消の通知に「問題を報告」を置ける", () => {
    const report = <ReportProblem onSubmit={() => {}} />;
    expect(render(<ErrorNotice onRetry={() => {}} report={report} />)).toContain("問題を報告");
    expect(render(<CancelledNotice onRetry={() => {}} report={report} />)).toContain("問題を報告");
    expect(render(<ErrorNotice onRetry={() => {}} />)).not.toContain("問題を報告");
  });

  it("保存したメッセージが無いターンでは出さない", () => {
    const started = applyEvent(newTurn("q"), { type: "run.started", run_id: "r", thread_id: "t", message_id: "m", model_id: "x" });
    expect(canReport(applyEvent(started, { type: "run.failed", code: "generation_failed", message: "失敗" }))).toBe(true);
    // 心拍が途絶えた run（runner_lost）はメッセージを保存していない
    expect(canReport(applyEvent(started, { type: "run.failed", code: "runner_lost", message: "中断" }))).toBe(false);
    // 受付前に取り消した（run.started が届いていない）
    expect(canReport({ ...newTurn("q"), status: "cancelled" })).toBe(false);
  });
});
