/** システムの処理（name="system"）の入力・出力の表示。 */
import type { Dictionary } from "@/i18n/dictionary";
import { KeyValueGrid, sectionLabelCls } from "./shared";

/** システムの処理の入力・出力。短い値は表に、長い文章（整形の前後・要約など）は読める箱に出す。 */
export function SystemFields({ data, t }: { data: Record<string, unknown>; t: Dictionary }) {
  const rows: { k: string; v: React.ReactNode }[] = [];
  const texts: [string, string][] = [];
  for (const [k, v] of Object.entries(data)) {
    if (k === "kind" || v === null || v === undefined) continue;
    if (typeof v === "string" && (v.length > 60 || v.includes("\n"))) texts.push([k, v]);
    else rows.push({ k: systemFieldLabel(k, t), v: systemValueLabel(k, v, t) });
  }
  return (
    <div className="space-y-2">
      {rows.length > 0 && <KeyValueGrid rows={rows} />}
      {texts.map(([k, v]) => (
        <div key={k}>
          <div className={sectionLabelCls}>{systemFieldLabel(k, t)}</div>
          <div className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
            {v.trim()}
          </div>
        </div>
      ))}
    </div>
  );
}

/** システムの処理の短い値。配列は「, 」でつなぎ、内訳から確かめた数字（number_check の derived）は式にする。 */
export function systemFieldValue(
  v: unknown,
  reasons: Record<string, string> = {},
  prune: { removed: string; kept: string; values: string; ignored?: string } = {
    removed: "-",
    kept: "+",
    values: "=",
  },
): string {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    // 社内システムの引数など（{"part": "SK-300"}）
    const kv = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== "" && x != null);
    return kv.length ? kv.map(([k, x]) => `${k}=${String(x)}`).join("・") : "—";
  }
  if (!Array.isArray(v)) return String(v);
  if (!v.length) return "—";
  return v
    .map((x) => {
      if (x && typeof x === "object" && "value" in x && Array.isArray((x as { from?: unknown }).from)) {
        const d = x as { value: unknown; op?: unknown; from: unknown[] };
        return `${String(d.value)} = ${d.from.map(String).join(d.op === "diff" ? " − " : " + ")}`;
      }
      if (x && typeof x === "object" && "sentence" in x && Array.isArray((x as { removed?: unknown }).removed)) {
        // 引用の刈り込み（specs/026 T31）: 文の冒頭・外した番号・残した番号・その文の値
        // 番号は検索で振った番号（保存のときに振り直される）なので、資料の名前があれば添える
        const d = x as {
          sentence: unknown;
          removed: unknown[];
          kept?: unknown[];
          values?: unknown[];
          ignored?: unknown[];
          documents?: Record<string, unknown>;
        };
        const docs = d.documents;
        const marks = (ns: unknown[] | undefined) =>
          docs
            ? (ns ?? []).map((n) => `[${String(n)}] ${String(docs[String(n)] ?? "")}`.trim()).join("、")
            : (ns ?? []).map((n) => `[${String(n)}]`).join("");
        // 質問に出た値は判断に使わない（specs/026 T34）
        const ignored = d.ignored?.length ? `／${prune.ignored ?? "?"}: ${d.ignored.map(String).join("・")}` : "";
        return `「${String(d.sentence)}」${prune.removed} ${marks(d.removed)}・${prune.kept} ${marks(d.kept)}（${prune.values}: ${(d.values ?? []).map(String).join("・")}${ignored}）`;
      }
      if (x && typeof x === "object" && "question" in x && "reason" in x) {
        // 落とした候補（続けて聞く）。理由は読める名前にし、根拠の語句があれば添える（specs/028 T23）
        const d = x as { question: unknown; reason: unknown; evidence?: unknown };
        const reason = reasons[String(d.reason)] ?? String(d.reason);
        return `${String(d.question)}（${reason}${typeof d.evidence === "string" ? `: 「${d.evidence}」` : ""}）`;
      }
      if (x && typeof x === "object" && "question" in x && "evidence" in x) {
        // 残した候補と根拠の語句
        const d = x as { question: unknown; evidence: unknown };
        return `${String(d.question)}（「${String(d.evidence)}」）`;
      }
      return String(x);
    })
    .join(", ");
}

/** 決まった値（空の生成の結果・未了の確認の種類）は読める名前にする。それ以外は systemFieldValue のまま。 */
export function systemValueLabel(key: string, v: unknown, t: Dictionary): string {
  const names = (t.chat.systemValues as Record<string, Record<string, string>>)[key];
  if (names && Array.isArray(v) && v.every((x) => typeof x === "string")) {
    return v.length ? v.map((x) => names[x] ?? x).join("・") : "—";
  }
  if (typeof v === "boolean" && names?.[String(v)]) return names[String(v)];
  return typeof v === "string" && names?.[v] ? names[v] : systemFieldValue(v, t.chat.droppedReasons, t.chat.pruneLabels);
}

export function systemFieldLabel(key: string, t: Dictionary): string {
  return (t.chat.systemFields as Record<string, string>)[key] ?? key;
}
