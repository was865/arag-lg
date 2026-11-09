"use client";

/** ヘルプ（specs/015-help-onboarding R1〜R4）。新版に実在する機能だけを説明する。 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { SHORTCUT_GROUPS } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

type Tab = "guide" | "shortcuts" | "tips";

const TABS: { id: Tab; label: string }[] = [
  { id: "guide", label: "使い方" },
  { id: "shortcuts", label: "ショートカット" },
  { id: "tips", label: "コツ" },
];

const FLOW = [
  {
    title: "質問する",
    body: "画面下の入力欄に、ふだんの言葉で質問します。入力欄の左で検索の範囲（すべての文書・ナレッジベース・1 つの文書）を選べます。",
  },
  {
    title: "検索の経過を見る",
    body: "エージェントが言い換え・検索・並べ替え・原文の読み込みを繰り返します。経過はその場で表示され、⌘⌫ か停止ボタンでいつでも止められます。",
  },
  {
    title: "出典で確かめる",
    body: "回答の [1] [2] が出典です。押すと右のパネルに該当する箇所が開きます。見つからないときは推測せず、その旨を答えます。",
  },
];

const FEATURES: { title: string; body: string }[] = [
  {
    title: "文書の追加",
    body: "サイドバーのナレッジベースを開き「追加」から。ファイルのほか、フォルダを中の構成ごと追加できます（ドラッグ＆ドロップも可）。",
  },
  {
    title: "回答のやり直し",
    body: "回答の下の「再生成」で作り直し、質問の「編集」で聞き直せます。どちらもその質問から先の会話を作り直します。",
  },
  {
    title: "評価",
    body: "👍 👎 で回答を評価できます。良くなかった理由を選ぶと、管理者が改善に使えます。",
  },
  {
    title: "共有と書き出し",
    body: "スレッドは「社内」か「リンクを知っている人」に共有できます。「自分のみ」に戻すと共有が止まります。回答はコピーや .md でも保存できます。",
  },
  {
    title: "ごみ箱",
    body: "削除した文書やフォルダはごみ箱に移り、元に戻せます。完全に削除すると戻せません。",
  },
  {
    title: "設定",
    body: "⌘, で開きます。テーマや出典の表示のほか、回答に使う資料の数などをこの端末向けに調整できます。",
  },
];

const DO = [
  ["条件を具体的に", "期間・部署・製品名などを入れると、検索の範囲が絞れて答えが正確になります。"],
  ["複数の質問は分ける", "「A の背景と B の今後」のような質問は、順番に聞くほうが正確です。"],
  ["社内の略語は展開する", "初めて出す略語は正式名も書くと、該当する文書に当たりやすくなります。"],
] as const;

const DONT = [
  ["範囲を広げすぎない", "関係する文書が分かっているなら、ナレッジベースや文書に絞ると速く正確になります。"],
  ["回答をうのみにしない", "出典を開いて、原文と解釈が合っているか確かめてください。"],
  ["共有範囲に注意", "「リンクを知っている人」はログインしていない人も読めます。共有されるのは会話そのものです。"],
] as const;

export function HelpModal({ onClose, onReplayTour }: { onClose: () => void; onReplayTour?: () => void }) {
  const [tab, setTab] = useState<Tab>("guide");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[230] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="ヘルプ"
        onClick={(e) => e.stopPropagation()}
        className="flex h-[min(640px,86vh)] w-[620px] max-w-full animate-pop-in flex-col overflow-hidden rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:h-[88dvh] max-md:w-full max-md:rounded-[18px_18px_0_0]"
      >
        <header className="flex items-center gap-2 px-5 pb-2 pt-3.5">
          <h2 className="m-0 flex-1 text-[15px] font-bold text-fg">ヘルプ</h2>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </header>
        <div role="tablist" aria-label="ヘルプの項目" className="flex gap-1 border-b-[0.5px] border-divider px-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              id={`help-tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls="help-panel"
              onClick={() => setTab(t.id)}
              className={cn(
                "-mb-px whitespace-nowrap border-b-2 px-2.5 py-2 text-[13px] font-medium",
                tab === t.id ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id="help-panel"
          aria-labelledby={`help-tab-${tab}`}
          className="min-h-0 flex-1 overflow-y-auto px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-4"
        >
          {tab === "guide" && <Guide onReplayTour={onReplayTour} />}
          {tab === "shortcuts" && <Shortcuts />}
          {tab === "tips" && <Tips />}
        </div>
      </div>
    </div>
  );
}

const H3 = "m-0 mb-2 text-[12px] font-semibold text-muted";

function Guide({ onReplayTour }: { onReplayTour?: () => void }) {
  return (
    <div className="flex flex-col gap-5">
      <section>
        <h3 className={H3}>基本の流れ</h3>
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {FLOW.map((s, i) => (
            <li key={s.title} className="flex gap-3 rounded-[12px] border-[0.5px] border-divider bg-surface-2/50 px-3.5 py-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent text-[12px] font-bold text-white">
                {i + 1}
              </span>
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-fg">{s.title}</div>
                <p className="m-0 mt-0.5 text-[12.5px] leading-relaxed text-fg-2">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
      <section>
        <h3 className={H3}>主な機能</h3>
        <dl className="m-0 grid grid-cols-2 gap-x-5 gap-y-3 max-md:grid-cols-1">
          {FEATURES.map((f) => (
            <div key={f.title}>
              <dt className="text-[13px] font-semibold text-fg">{f.title}</dt>
              <dd className="m-0 mt-0.5 text-[12.5px] leading-relaxed text-fg-2">{f.body}</dd>
            </div>
          ))}
        </dl>
      </section>
      {onReplayTour && (
        <div>
          <button
            onClick={onReplayTour}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 text-[12.5px] font-medium text-fg hover:bg-surface-2"
          >
            はじめてのガイドをもう一度見る
          </button>
        </div>
      )}
    </div>
  );
}

function Shortcuts() {
  return (
    <div className="flex flex-col gap-5">
      <p className="m-0 text-[12.5px] text-muted">Windows・Linux では ⌘ を Ctrl に読み替えてください。</p>
      {SHORTCUT_GROUPS.map((g) => (
        <section key={g.title}>
          <h3 className={H3}>{g.title}</h3>
          <ul className="m-0 list-none p-0">
            {g.items.map((it) => (
              <li
                key={it.keys}
                className="flex items-center justify-between gap-3 border-b-[0.5px] border-divider py-2 text-[13px] last:border-b-0"
              >
                <span className="text-fg-2">{it.label}</span>
                <kbd className="rounded-md border-[0.5px] border-divider-strong bg-surface-2 px-1.5 py-0.5 font-mono text-[12px] text-fg">
                  {it.keys}
                </kbd>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Tips() {
  return (
    <div className="flex flex-col gap-5">
      <TipList title="おすすめ" mark="✓" tone="text-[#3c9a5f]" items={DO} />
      <TipList title="気をつけること" mark="!" tone="text-accent" items={DONT} />
    </div>
  );
}

function TipList({
  title,
  mark,
  tone,
  items,
}: {
  title: string;
  mark: string;
  tone: string;
  items: readonly (readonly [string, string])[];
}) {
  return (
    <section>
      <h3 className={H3}>{title}</h3>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {items.map(([t, b]) => (
          <li key={t} className="flex gap-2.5">
            <span aria-hidden className={cn("w-4 shrink-0 text-center text-[13px] font-bold", tone)}>
              {mark}
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-fg">{t}</div>
              <p className="m-0 mt-0.5 text-[12.5px] leading-relaxed text-fg-2">{b}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
