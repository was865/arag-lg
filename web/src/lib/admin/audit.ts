/** 監査ログの表示（specs/011-audit-log R5）。 */
import { ROLE_LABEL, type Role } from "@/lib/admin/members";
import { ROLE_LABEL as SHARE_ROLE_LABEL, type ShareRole } from "@/lib/access/shares";
import { VISIBILITY_OPTIONS } from "@/lib/share";

export const ACTION_LABEL: Record<string, string> = {
  "document.delete": "文書をごみ箱へ",
  "document.restore": "文書を元に戻す",
  "document.purge": "文書を完全に削除",
  "folder.delete": "フォルダをごみ箱へ",
  "folder.restore": "フォルダを元に戻す",
  "folder.purge": "フォルダを完全に削除",
  "kb.create": "ナレッジベースを作成",
  "kb.delete": "ナレッジベースを削除",
  "kb.restore": "ナレッジベースを元に戻す",
  "kb.archive": "ナレッジベースをアーカイブ",
  "kb.unarchive": "ナレッジベースのアーカイブを解除",
  "kb.share_add": "共有先を追加",
  "kb.share_change": "共有の役割を変更",
  "kb.share_remove": "共有先を削除",
  "department.create": "部門を作成",
  "department.rename": "部門の名前を変更",
  "department.delete": "部門を削除",
  "department.member_add": "部門にメンバーを追加",
  "department.member_role": "部門での役割を変更",
  "department.member_remove": "部門からメンバーを削除",
  "gc.purge": "期限切れの完全削除",
  "thread.share": "スレッドの公開範囲を変更",
  "chat.run": "質問",
  "member.invite": "メンバーを招待",
  "member.role": "役割を変更",
  "member.ban": "メンバーを停止",
  "member.unban": "メンバーを再開",
  "member.resend_invite": "招待を再送",
  "llm.credential.create": "LLM の接続を追加",
  "llm.credential.update": "LLM の接続を変更",
  "llm.credential.delete": "LLM の接続を削除",
  "llm.model.create": "モデルを追加",
  "llm.model.update": "モデルを変更",
  "llm.model.delete": "モデルを削除",
  "llm.model.reorder": "モデルを並べ替え",
  "mcp.server.create": "社内システムを登録",
  "mcp.server.update": "社内システムを変更",
  "mcp.server.delete": "社内システムを削除",
  "mcp.server.refresh": "社内システムのツールを読み直し",
  "mcp.server.tools": "社内システムのツールを選択",
  "mcp.server.shares": "社内システムの使える範囲を変更",
  "feedback.resolve": "報告を対応済みに",
  "feedback.reopen": "報告を未対応に戻す",
};

/** 絞り込みの選択肢（前方一致で API に渡す）。 */
export const ACTION_GROUPS: { value: string; label: string }[] = [
  { value: "", label: "すべての操作" },
  { value: "document.", label: "文書" },
  { value: "folder.", label: "フォルダ" },
  { value: "kb.", label: "ナレッジベース" },
  { value: "member.", label: "メンバー管理" },
  { value: "department.", label: "部門" },
  { value: "llm.", label: "モデル・API キー" },
  { value: "mcp.", label: "社内システム" },
  { value: "thread.", label: "共有" },
  { value: "chat.", label: "質問" },
  { value: "feedback.", label: "フィードバック" },
];

export function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action;
}

const role = (r: unknown) => ROLE_LABEL[r as Role] ?? String(r);
const DEPT_ROLE_LABEL: Record<string, string> = { member: "メンバー", manager: "部門管理者" };
const SUBJECT_LABEL: Record<string, string> = { everyone: "全員", department: "部門", user: "人" };

export function describeTarget(row: {
  resource_type: string | null;
  resource_id: string | null;
  detail: Record<string, unknown> | null | undefined;
}): string {
  const d = row.detail ?? {};
  const base =
    typeof d.email === "string"
      ? d.email
      : typeof d.label === "string"
        ? d.label
        : row.resource_type || row.resource_id
          ? [row.resource_type, row.resource_id].filter(Boolean).join(" ")
          : "";
  const notes: string[] = [];
  if (typeof d.subject_type === "string") {
    // 共有リストの変更（specs/024）。役割は 閲覧・編集・管理、無ければ「なし」
    const sr = (r: unknown) => (r == null ? "なし" : (SHARE_ROLE_LABEL[r as ShareRole] ?? String(r)));
    notes.push(`${SUBJECT_LABEL[d.subject_type] ?? d.subject_type}: ${sr(d.from)} → ${sr(d.to)}`);
  } else if (typeof d.user_id === "string" && row.resource_type === "department") {
    if (d.role !== undefined) notes.push(DEPT_ROLE_LABEL[String(d.role)] ?? String(d.role));
  } else if (d.from !== undefined && d.to !== undefined) notes.push(`${role(d.from)} → ${role(d.to)}`);
  else if (d.role !== undefined) notes.push(role(d.role));
  if (d.key_rotated === true) notes.push("キーを入れ替え");
  if (typeof d.visibility === "string") {
    notes.push(VISIBILITY_OPTIONS.find((o) => o.id === d.visibility)?.label ?? d.visibility);
  }
  if (!base && !notes.length) return "—";
  return notes.length ? `${base}（${notes.join("・")}）` : base;
}

/** 日付の入力（YYYY-MM-DD）を API の from・to（to はその翌日 0 時の手前まで）にする。 */
export function toRangeQuery(from: string, to: string): { from?: string; to?: string } {
  const day = (s: string, plus = 0) => {
    const [y, m, d] = s.split("-").map(Number);
    return new Date(y!, (m ?? 1) - 1, (d ?? 1) + plus).toISOString();
  };
  return { from: from ? day(from) : undefined, to: to ? day(to, 1) : undefined };
}
