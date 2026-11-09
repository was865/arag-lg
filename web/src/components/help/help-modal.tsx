"use client";

/** ヘルプ（specs/015-help-onboarding R1〜R4）。旧版のレイアウト（左のナビ・概要・手順・機能カード）を移植し、
 *  文言は新版に実在する機能だけに直した。ショートカットはキー判定と同じ定義から作る。 */
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/icons";
import { keyParts, SHORTCUT_GROUPS, SHORTCUT_LABEL } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import type { WorkspaceStats } from "@/lib/workspace-stats";

type Tab = "overview" | "workflow" | "features" | "shortcuts" | "tips";

const TABS: { id: Tab; label: string; icon: NavIconName }[] = [
  { id: "overview", label: "概要", icon: "sparkles" },
  { id: "workflow", label: "基本の流れ", icon: "route" },
  { id: "features", label: "主な機能", icon: "layers" },
  { id: "shortcuts", label: "ショートカット", icon: "keyboard" },
  { id: "tips", label: "うまく使うコツ", icon: "lightbulb" },
];

const nf = new Intl.NumberFormat("ja-JP");

export function HelpModal({
  onClose,
  onReplayTour,
  stats,
}: {
  onClose: () => void;
  onReplayTour?: () => void;
  stats?: WorkspaceStats | null;
}) {
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[230] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.48)] p-6 motion-reduce:animate-none max-md:p-0"
      role="dialog"
      aria-modal="true"
      aria-label="ヘルプ"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="grid h-[min(680px,92vh)] w-[min(960px,100%)] animate-pop-in grid-cols-[220px_minmax(0,1fr)] overflow-hidden rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-[0_30px_80px_rgba(0,0,0,0.32)] motion-reduce:animate-none max-md:h-dvh max-md:max-h-dvh max-md:w-full max-md:grid-cols-[minmax(0,1fr)] max-md:grid-rows-[auto_minmax(0,1fr)] max-md:rounded-none max-md:border-0">
        <aside className="flex min-w-0 flex-col border-r-[0.5px] border-divider bg-surface-2 p-[18px_12px_14px] max-md:flex-row max-md:items-center max-md:gap-2 max-md:border-b-[0.5px] max-md:border-r-0 max-md:p-2.5 max-md:pt-[max(10px,env(safe-area-inset-top))]">
          <div className="mb-2.5 flex items-center gap-2.5 border-b-[0.5px] border-divider px-2 pb-3.5 pt-0.5 max-md:m-0 max-md:shrink-0 max-md:border-b-0 max-md:border-r-[0.5px] max-md:px-1 max-md:pb-0 max-md:pr-2.5">
            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-accent text-white">
              <BrandMark size={15} />
            </div>
            <div className="max-md:hidden">
              <div className="text-[14px] font-bold tracking-[-0.01em] text-fg">ARag</div>
              <div className="mt-px font-mono text-[10.5px] text-muted">ヘルプ</div>
            </div>
          </div>
          <nav
            role="tablist"
            aria-label="ヘルプの項目"
            className="flex flex-1 flex-col gap-0.5 max-md:min-w-0 max-md:flex-row max-md:gap-1 max-md:overflow-x-auto max-md:[scrollbar-width:none]"
          >
            {TABS.map((tb) => (
              <button
                key={tb.id}
                role="tab"
                aria-selected={tab === tb.id}
                onClick={() => setTab(tb.id)}
                className={cn(
                  "flex items-center gap-2.5 whitespace-nowrap rounded-lg border-0 bg-transparent px-2.5 py-2 text-left text-[13px] font-medium transition-colors max-md:shrink-0 max-md:text-[12.5px]",
                  tab === tb.id
                    ? "bg-surface font-semibold text-fg shadow-e1 [&_svg]:text-accent"
                    : "text-fg-2 hover:bg-divider hover:text-fg",
                )}
              >
                <NavIcon name={tb.icon} />
                <span>{tb.label}</span>
              </button>
            ))}
          </nav>
          {onReplayTour && (
            <div className="border-t-[0.5px] border-divider pt-2.5 max-md:hidden">
              <ReplayButton onClick={onReplayTour} />
            </div>
          )}
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="hidden h-[30px] w-[30px] shrink-0 place-items-center rounded-lg text-muted hover:bg-divider hover:text-fg max-md:grid"
          >
            <CloseIcon />
          </button>
        </aside>

        <section className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)]">
          <header className="flex items-center justify-between border-b-[0.5px] border-divider px-7 pb-3.5 pt-[18px] max-md:px-4 max-md:pb-3 max-md:pt-3.5">
            <h2 className="m-0 text-[18px] font-bold tracking-[-0.015em] text-fg max-md:text-[16px]">
              {TABS.find((tb) => tb.id === tab)?.label}
            </h2>
            <button
              onClick={onClose}
              aria-label="閉じる"
              className="grid h-[30px] w-[30px] place-items-center rounded-lg text-muted hover:bg-divider hover:text-fg max-md:hidden"
            >
              <CloseIcon />
            </button>
          </header>
          <div className="overflow-y-auto px-7 pb-7 pt-[22px] max-md:px-4 max-md:pb-[max(24px,env(safe-area-inset-bottom))] max-md:pt-4">
            {tab === "overview" && <Overview onJump={setTab} stats={stats} onReplayTour={onReplayTour} />}
            {tab === "workflow" && <Workflow />}
            {tab === "features" && <Features />}
            {tab === "shortcuts" && <Shortcuts />}
            {tab === "tips" && <Tips />}
          </div>
        </section>
      </div>
    </div>
  );
}

const lead = "m-0 text-[13.5px] leading-[1.65] text-fg-2 [&_strong]:font-semibold [&_strong]:text-fg";

// ── 概要 ─────────────────────────────────────────────────────────────────

function Overview({
  onJump,
  stats,
  onReplayTour,
}: {
  onJump: (t: Tab) => void;
  stats?: WorkspaceStats | null;
  onReplayTour?: () => void;
}) {
  const hero = [
    { n: stats ? nf.format(stats.indexedDocumentCount) : "—", l: "検索できる文書" },
    { n: stats ? nf.format(stats.kbCount) : "—", l: "ナレッジベース" },
    {
      n: stats ? nf.format(Math.max(0, stats.totalDocumentCount - stats.indexedDocumentCount)) : "—",
      l: "未完了",
    },
  ];
  const cards: { n: string; t: Tab; title: string; desc: string }[] = [
    { n: "01", t: "workflow", title: "基本の流れ", desc: "質問 → 検索の経過 → 出典付きの回答までの 3 ステップ。" },
    { n: "02", t: "features", title: "主な機能", desc: "範囲の指定・文書の追加・出典パネル・やり直し・共有。" },
    { n: "03", t: "shortcuts", title: "ショートカット", desc: "⇧⌘O・⌘B・⌘, など、手を止めずに操作するキー。" },
    { n: "04", t: "tips", title: "うまく使うコツ", desc: "質問の書き方と、気をつけたい使い方。" },
  ];
  return (
    <div className="flex flex-col gap-[22px]">
      <div className="flex flex-col gap-3.5 rounded-[14px] border-[0.5px] border-divider-strong bg-gradient-to-b from-surface-2 to-surface p-[22px_24px_24px] max-md:p-4">
        <div className="self-start rounded-full border-[0.5px] border-accent/55 bg-accent/[0.08] px-[9px] py-[3px] font-mono text-[10px] font-bold tracking-[0.12em] text-accent">
          AGENTIC RAG
        </div>
        <h3 className="m-0 text-[22px] font-bold leading-[1.25] tracking-[-0.02em] text-fg max-md:text-[19px]">
          社内の文書を調べて、出典付きで答えます。
        </h3>
        <p className={cn(lead, "max-w-[58ch]")}>
          ARag は<strong>エージェント型の検索アシスタント</strong>
          です。質問を受けると、言い換え・検索（意味とキーワードの両方）・並べ替え・原文の読み込みを必要なだけ繰り返し、
          <strong>根拠の箇所を示した回答</strong>を返します。資料に無いことは推測せず、見つからないと答えます。
          日本語の文書に最適化していますが、英語の文書や日英をまたぐ質問にも答えます。
        </p>
        <div className="mt-1.5 grid grid-cols-3 gap-px overflow-hidden rounded-[10px] border-[0.5px] border-divider bg-divider">
          {hero.map((s) => (
            <div key={s.l} className="min-w-0 bg-surface px-3.5 py-3 max-md:px-2.5">
              <div className="truncate font-mono text-[19px] font-bold tracking-[-0.02em] text-accent max-md:text-[16px]">
                {s.n}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-muted">{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2.5 max-md:grid-cols-1">
        {cards.map((c) => (
          <button
            key={c.n}
            onClick={() => onJump(c.t)}
            className="group/jc flex items-center gap-3.5 rounded-xl border-[0.5px] border-divider-strong bg-surface px-4 py-3.5 text-left transition-[border-color,background,transform] hover:-translate-y-px hover:border-accent hover:bg-accent-soft"
          >
            <div className="font-mono text-[11px] font-semibold tracking-[0.04em] text-muted">{c.n}</div>
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] font-semibold tracking-[-0.005em] text-fg">{c.title}</div>
              <div className="mt-[3px] text-[11.5px] leading-[1.5] text-muted">{c.desc}</div>
            </div>
            <span className="inline-flex text-accent opacity-60 transition-[transform,opacity] group-hover/jc:translate-x-[3px] group-hover/jc:opacity-100">
              <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
                <path d="M5 3l5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          </button>
        ))}
      </div>
      {onReplayTour && (
        <div className="md:hidden">
          <ReplayButton onClick={onReplayTour} />
        </div>
      )}
    </div>
  );
}

// ── 基本の流れ ───────────────────────────────────────────────────────────

const STEPS = [
  {
    n: "01",
    title: "質問を入力する",
    body: "画面下の入力欄に、ふだんの言葉で質問します。いつ・どこで・何の、といった条件を入れるほど正確になります。",
    hint: "入力欄の左の範囲ボタンで、すべての文書・ナレッジベース・1 つの文書から調べる範囲を選べます。",
  },
  {
    n: "02",
    title: "エージェントが資料をたどる",
    body: "言い換え → 意味とキーワードの検索 → 並べ替え → 原文の読み込みを、関連する資料が揃うまで繰り返します。経過はその場で表示されます。",
    hint: "方向がずれたら ⌘⌫ か停止ボタンですぐ止められます。経過の見せ方は設定で変えられます。",
  },
  {
    n: "03",
    title: "出典付きの回答を受け取る",
    body: "回答の [1] [2] が出典です。押すと右のパネルで原文の該当箇所が開き、根拠を確かめられます。",
    hint: "👍 👎 で評価、コピー・.md で保存、再生成や質問の編集で聞き直せます。",
  },
];

function Workflow() {
  return (
    <div className="flex flex-col gap-[22px]">
      <p className={lead}>
        ARag は <strong>3 つの段階</strong>で動きます。どの段階も画面に表示され、いつでも止められます。
      </p>
      <ol className="m-0 ml-3 flex list-none flex-col border-l-[0.5px] border-dashed border-divider-strong p-0">
        {STEPS.map((s) => (
          <li key={s.n} className="grid grid-cols-[56px_minmax(0,1fr)] pb-[22px] last:pb-0 max-md:grid-cols-[40px_minmax(0,1fr)]">
            <div className="-ml-[19px] grid h-[38px] w-[38px] place-items-center rounded-full border-[1.5px] border-accent bg-surface font-mono text-[11.5px] font-bold tracking-[-0.01em] text-accent">
              {s.n}
            </div>
            <div className="pl-1 pt-1.5">
              <div className="text-[15px] font-semibold tracking-[-0.01em] text-fg">{s.title}</div>
              <p className="my-1.5 mb-2.5 text-[13px] leading-[1.65] text-fg-2">{s.body}</p>
              <div className="flex items-start gap-2.5 rounded-[0_8px_8px_0] border-l-2 border-accent bg-surface-2 px-3 py-2.5 text-[12px] leading-[1.6] text-fg-2">
                <span className="shrink-0 pt-px font-mono text-[10px] font-bold tracking-[0.08em] text-accent">TIP</span>
                <span>{s.hint}</span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── 主な機能 ─────────────────────────────────────────────────────────────

const FEATURES: { icon: FeatIconName; title: string; body: string }[] = [
  {
    icon: "scope",
    title: "検索の範囲",
    body: "入力欄の左で、すべての文書・ナレッジベース・1 つの文書から選べます。アーカイブした文書を含めることもできます。広すぎる範囲は雑音のもとなので、まず狭く始めるのがおすすめです。",
  },
  {
    icon: "upload",
    title: "文書の追加",
    body: "ナレッジベースを開いて「追加」から。PDF・Word・Excel・PowerPoint・Markdown などを、フォルダごと中の構成のまま追加できます（ドラッグ＆ドロップも可）。画像の説明が有効な環境では、図の内容も検索できます。",
  },
  {
    icon: "steps",
    title: "検索の経過",
    body: "言い換え・検索・読み込みの各段階を表示します。設定で「カード」「タイムライン」「ログ」の 3 種類から見せ方を選べます。",
  },
  {
    icon: "cite",
    title: "出典パネル",
    body: "回答の [1] [2] を押すと右のパネルが開き、原文の該当箇所が示されます。文書の全体もその場で開けます。",
  },
  {
    icon: "thread",
    title: "スレッドとやり直し",
    body: "過去の質問はサイドバーからすぐ開け、検索・名前の変更・星印での固定ができます。再生成や質問の編集で、その質問から先を作り直せます。",
  },
  {
    icon: "share",
    title: "共有と書き出し",
    body: "スレッドは「社内」か「リンクを知っている人」に共有できます。「自分のみ」に戻すと共有が止まります。回答はコピーや .md でも保存できます。",
  },
];

function Features() {
  return (
    <div className="flex flex-col gap-[22px]">
      <p className={lead}>
        どの機能も、<strong>少ない操作で根拠までたどる</strong>ことを目的にしています。
      </p>
      <div className="grid grid-cols-2 gap-2.5 max-md:grid-cols-1">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="grid grid-cols-[36px_minmax(0,1fr)] gap-3 rounded-xl border-[0.5px] border-divider-strong bg-surface p-3.5"
          >
            <div className="grid h-9 w-9 place-items-center rounded-[9px] bg-accent/[0.08] text-accent">
              <FeatIcon name={f.icon} />
            </div>
            <div>
              <div className="text-[13.5px] font-semibold tracking-[-0.005em] text-fg">{f.title}</div>
              <p className="m-0 mt-1 text-[12.5px] leading-[1.6] text-muted">{f.body}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── ショートカット ───────────────────────────────────────────────────────

function Shortcuts() {
  return (
    <div className="flex flex-col gap-[22px]">
      <p className={lead}>
        <strong>⌘</strong> は macOS のキーです。Windows・Linux では <strong>Ctrl</strong> に読み替えてください。
        <strong> ?</strong> は入力欄の外で押したときに効きます。
      </p>
      <div className="flex flex-col gap-4">
        {SHORTCUT_GROUPS.map((g) => (
          <div key={g.title} className="flex flex-col gap-2">
            <div className="font-mono text-[10.5px] font-bold uppercase tracking-[0.1em] text-accent">{g.title}</div>
            <div className="overflow-hidden rounded-[10px] border-[0.5px] border-divider-strong">
              {g.items.map((it) => (
                <div
                  key={it.keys}
                  className="grid grid-cols-[180px_minmax(0,1fr)] items-center border-b-[0.5px] border-divider bg-surface px-3.5 py-2.5 text-[13px] last:border-b-0 max-md:grid-cols-[130px_minmax(0,1fr)]"
                >
                  <div className="flex items-center gap-1">
                    {keyParts(it.keys).map((k, j, all) => (
                      <span key={j} className="flex items-center gap-1">
                        <Kbd>{k}</Kbd>
                        {j < all.length - 1 && <span className="font-mono text-[11px] text-muted-2">+</span>}
                      </span>
                    ))}
                  </div>
                  <div className="text-[12.5px] text-fg-2">{it.label}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── コツ ─────────────────────────────────────────────────────────────────

const TIPS: { kind: "do" | "dont"; title: string; body: string }[] = [
  {
    kind: "do",
    title: "条件を具体的に入れる",
    body: "「2025 年度の」「第 2 工場の」など、期間・場所・対象を書くと検索の範囲が絞れます。",
  },
  {
    kind: "do",
    title: "複数の質問は分ける",
    body: "「A の背景と B の今後」のような質問は精度が下がります。順番に聞くか、スレッドを分けましょう。",
  },
  {
    kind: "do",
    title: "社内の略語は展開する",
    body: "初めて出す略語は正式名も書くと、該当する文書に当たりやすくなります。",
  },
  {
    kind: "dont",
    title: "共有範囲の確認を忘れる",
    body: "「リンクを知っている人」はログインしていない人も読めます。共有されるのは会話そのものです。",
  },
  {
    kind: "dont",
    title: "いつも全文書で探す",
    body: "関係する文書が分かっているなら、ナレッジベースや文書に絞ると速く正確になります。",
  },
  {
    kind: "dont",
    title: "回答をうのみにする",
    body: "出典を開いて、原文と解釈が合っているか確かめてください。👎 と理由は改善に使われます。",
  },
];

function Tips() {
  return (
    <div className="flex flex-col gap-[22px]">
      <p className={lead}>質問の書き方ひとつで、回答の速さと正確さは大きく変わります。</p>
      <div className="grid grid-cols-2 gap-2.5 max-md:grid-cols-1">
        {TIPS.map((tip) => (
          <div
            key={tip.title}
            className="grid grid-cols-[28px_minmax(0,1fr)] gap-3 rounded-xl border-[0.5px] border-divider-strong bg-surface p-3.5"
          >
            <div
              className={cn(
                "grid h-7 w-7 place-items-center rounded-full",
                tip.kind === "do" ? "bg-accent-soft text-accent" : "bg-[rgba(192,83,58,0.13)] text-[#C0533A]",
              )}
            >
              {tip.kind === "do" ? (
                <svg viewBox="0 0 16 16" width="13" height="13">
                  <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : (
                <svg viewBox="0 0 16 16" width="13" height="13">
                  <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              )}
            </div>
            <div>
              <div
                className={cn(
                  "font-mono text-[10px] font-bold tracking-[0.1em]",
                  tip.kind === "do" ? "text-accent" : "text-[#C0533A]",
                )}
              >
                {tip.kind === "do" ? "DO" : "DON'T"}
              </div>
              <div className="mt-0.5 text-[13.5px] font-semibold tracking-[-0.005em] text-fg">{tip.title}</div>
              <p className="m-0 mt-1.5 text-[12px] leading-[1.6] text-muted">{tip.body}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-1 flex items-center justify-between gap-3.5 rounded-xl border-[0.5px] border-accent/40 bg-accent/[0.05] px-[18px] py-3.5 max-md:flex-col max-md:items-start">
        <div>
          <div className="text-[13.5px] font-semibold tracking-[-0.005em] text-fg">まずは試してみる</div>
          <div className="mt-0.5 text-[11.5px] leading-[1.5] text-muted">
            新しいスレッドの下にあるヒントから、エージェントの動きを体験できます。
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {keyParts(SHORTCUT_LABEL.newThread).map((k, j, all) => (
            <span key={j} className="flex items-center gap-1">
              <Kbd>{k}</Kbd>
              {j < all.length - 1 && <span className="font-mono text-[11px] text-muted-2">+</span>}
            </span>
          ))}
          <span className="ml-2 text-[12px] text-muted">で新しいスレッド</span>
        </div>
      </div>
    </div>
  );
}

// ── 部品 ─────────────────────────────────────────────────────────────────

function ReplayButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-[7px] border-0 bg-transparent px-2.5 py-[7px] text-left text-[12px] text-muted transition-colors hover:bg-divider hover:text-fg-2 max-md:border-[0.5px] max-md:border-divider-strong max-md:py-2.5"
    >
      <span>はじめてのガイドをもう一度見る</span>
      <svg viewBox="0 0 16 16" width="11" height="11">
        <path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9M2.5 1.5v3h3" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-grid h-[22px] min-w-[22px] place-items-center rounded-[5px] border-[0.5px] border-b-[1.5px] border-divider-strong bg-surface px-1.5 font-mono text-[11px] font-semibold text-fg-2 shadow-[0_1px_0_var(--divider)]">
      {children}
    </kbd>
  );
}

type NavIconName = "sparkles" | "route" | "layers" | "keyboard" | "lightbulb";
function NavIcon({ name }: { name: NavIconName }) {
  const p = {
    viewBox: "0 0 16 16",
    width: 14,
    height: 14,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "shrink-0 opacity-85",
  };
  if (name === "sparkles")
    return (
      <svg {...p}>
        <path d="M8 2v3M8 11v3M2 8h3M11 8h3M4 4l2 2M10 10l2 2M4 12l2-2M10 6l2-2" />
      </svg>
    );
  if (name === "route")
    return (
      <svg {...p}>
        <circle cx="4" cy="4" r="1.5" />
        <circle cx="12" cy="12" r="1.5" />
        <path d="M4 5.5v3a3 3 0 003 3h2a3 3 0 013 3" />
      </svg>
    );
  if (name === "layers")
    return (
      <svg {...p}>
        <path d="M8 2 2 5l6 3 6-3-6-3z" />
        <path d="m2 8 6 3 6-3M2 11l6 3 6-3" />
      </svg>
    );
  if (name === "keyboard")
    return (
      <svg {...p}>
        <rect x="2" y="4.5" width="12" height="7" rx="1.5" />
        <path d="M4.5 7h.01M7 7h.01M9.5 7h.01M12 7h.01M5 9.5h6" />
      </svg>
    );
  return (
    <svg {...p}>
      <path d="M6 13h4M6.5 11h3M5 8.5A3.5 3.5 0 118 5a3.5 3.5 0 013 5.5" />
    </svg>
  );
}

type FeatIconName = "scope" | "upload" | "steps" | "cite" | "thread" | "share";
function FeatIcon({ name }: { name: FeatIconName }) {
  const p = {
    viewBox: "0 0 20 20",
    width: 18,
    height: 18,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (name === "scope")
    return (
      <svg {...p}>
        <circle cx="10" cy="10" r="6" />
        <circle cx="10" cy="10" r="2.2" />
        <path d="M10 2v2M10 16v2M2 10h2M16 10h2" />
      </svg>
    );
  if (name === "upload")
    return (
      <svg {...p}>
        <path d="M3 13v2.5A1.5 1.5 0 004.5 17h11a1.5 1.5 0 001.5-1.5V13" />
        <path d="M10 13V3M6 7l4-4 4 4" />
      </svg>
    );
  if (name === "steps")
    return (
      <svg {...p}>
        <path d="M3 5h6M3 10h10M3 15h14" />
        <circle cx="9" cy="5" r="1.2" fill="currentColor" />
        <circle cx="13" cy="10" r="1.2" fill="currentColor" />
        <circle cx="17" cy="15" r="1.2" fill="currentColor" />
      </svg>
    );
  if (name === "cite")
    return (
      <svg {...p}>
        <path d="M3 4h11v8H8l-3 3v-3H3z" />
        <path d="M6.5 7.5h5M6.5 9.5h3" />
      </svg>
    );
  if (name === "thread")
    return (
      <svg {...p}>
        <path d="M3 5h14M3 10h10M3 15h12" />
      </svg>
    );
  return (
    <svg {...p}>
      <circle cx="5" cy="10" r="2" />
      <circle cx="15" cy="5" r="2" />
      <circle cx="15" cy="15" r="2" />
      <path d="M6.7 9.1 13.3 5.9M6.7 10.9l6.6 3.2" />
    </svg>
  );
}
