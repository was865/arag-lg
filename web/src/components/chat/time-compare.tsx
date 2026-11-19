"use client";
/**
 * 時点の比較の表（specs/033 R20）。回答の同じ文に文書の値と社内システムの値が並んでいたら、時点を添えて並べる。
 * 判定は lib/chat/compare の純関数（見つからなければ何も出さない）。印を押すと出典を開く。
 */
import { useT } from "@/i18n/context";
import { compareRows } from "@/lib/chat/compare";
import { formatFetchedAt } from "@/lib/datetime";
import type { CitationMap, Source } from "@/lib/types";

export function TimeCompare({
  answer,
  citationMap,
  sources,
  onCite,
}: {
  answer: string;
  citationMap: CitationMap;
  sources: Source[];
  onCite: (n: number) => void;
}) {
  const { t } = useT();
  const rows = compareRows(answer, citationMap, sources);
  if (rows.length === 0) return null;
  const cite = (n: number) => (
    <button
      type="button"
      onClick={() => onCite(n)}
      className="ml-1 cursor-pointer border-0 bg-transparent p-0 font-mono text-caption text-accent hover:underline"
    >
      [{n}]
    </button>
  );
  return (
    <section className="flex flex-col gap-1.5" aria-label={t.chat.compareTitle}>
      <div className="eyebrow">{t.chat.compareTitle}</div>
      <div className="overflow-x-auto rounded-control border-[0.5px] border-divider">
        <table className="w-full border-collapse text-caption">
          <thead>
            <tr className="text-left text-muted">
              <th className="px-2.5 py-1.5 font-semibold">{t.chat.compareItem}</th>
              <th className="px-2.5 py-1.5 font-semibold">{t.chat.compareDoc}</th>
              <th className="px-2.5 py-1.5 font-semibold">{t.chat.compareSystem}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.item} className="border-t-[0.5px] border-divider align-top">
                <td className="px-2.5 py-1.5 text-fg">{r.item}</td>
                <td className="px-2.5 py-1.5">
                  <span className="font-semibold tabular-nums text-fg">{r.doc.value}</span>
                  {cite(r.doc.n)}
                  <div className="text-muted">{r.doc.title}</div>
                </td>
                <td className="px-2.5 py-1.5">
                  <span className="font-semibold tabular-nums text-fg">{r.system.value}</span>
                  {cite(r.system.n)}
                  <div className="text-muted">
                    {r.system.title}
                    {r.system.at ? `・${formatFetchedAt(r.system.at)}` : ""}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.some((r) => !r.same) && <div className="text-caption text-muted">{t.chat.compareNote}</div>}
    </section>
  );
}
