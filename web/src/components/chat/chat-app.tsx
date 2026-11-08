"use client";

/** チャット画面（specs/005-agent D4〜D6）。旧版 workspace の見た目を保ち、データ層だけを新しい API に載せ替えた。
 *
 * - URL は `/`（新規）と `/c/<threadId>`。切り替えは history.pushState で行い、画面は再マウントしない
 *   （生成中の run の購読を保つため）。再読み込みすると active-run から続きを表示する。
 * - 文書の管理画面・設定・認証は P4 で移植する。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { Sidebar } from "@/components/sidebar/sidebar";
import { LibraryView } from "@/components/library/library-view";
import { TrashView } from "@/components/library/trash-view";
import { parseRoute, routePath, type Route } from "@/lib/routes";
import { ThemeToggle } from "@/components/sidebar/theme-toggle";
import { Composer } from "@/components/chat/composer";
import { EmptyState } from "@/components/chat/empty-state";
import { Transcript } from "@/components/chat/messages";
import { RightPanel, type RightPanelAction } from "@/components/sources/right-panel";
import { originalUrl } from "@/components/documents/original-preview";
import { useToast } from "@/components/feedback/toast-provider";
import { useConfirm } from "@/hooks/use-confirm";
import { useConversations, NEW_THREAD } from "@/hooks/use-conversations";
import { useKbs } from "@/hooks/use-kbs";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTweaks } from "@/hooks/use-tweaks";
import { usePanelWidth } from "@/components/workspace/use-panel-width";
import { chatApi, type ThreadOut } from "@/lib/chat/api";
import { MODEL_STORAGE_KEY } from "@/lib/constants";
import { shortcutAction } from "@/lib/shortcuts";
import type { FeedbackRating, FeedbackReasonTag, TurnFeedback } from "@/lib/feedback-types";
import type { AppUser, ModelOption, ScopeValue, Source, ThreadSummary, Turn } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";
import { EMPTY_STATS, normalizeStats, type WorkspaceStats } from "@/lib/workspace-stats";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";

// P3 は開発用の利用者（中継が X-Dev-User-Id を付ける）。P4 で Better Auth のセッションに置き換える
const DEV_USER: AppUser = {
  name: "開発ユーザー",
  firstName: "開発ユーザー",
  org: "ARag",
  initials: "開",
  email: "dev@example.com",
  onboardedAt: null,
  emailVerifiedAt: null,
};

const LOADING_MODEL: ModelOption = { id: "", label: "読み込み中…", tag: "", desc: "", available: false };
const NO_MODEL: ModelOption = { id: "", label: "モデル未設定", tag: "", desc: "", available: false };

function toSummary(t: ThreadOut): ThreadSummary {
  return { id: t.id, title: t.title, pinned: t.pinned, updated: relativeTime(new Date(t.updated_at)) };
}

export function ChatApp({ initialRoute }: { initialRoute: Route }) {
  const { t } = useT();
  const push = useToast();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { tweaks, setTweak } = useTweaks();
  const { kbs } = useKbs();
  const [panelWidth, handleResizeWidth] = usePanelWidth();
  const isMobile = useMediaQuery("(max-width: 768px)");
  const isWide = useMediaQuery("(min-width: 1181px)");

  const [threads, setThreads] = useState<ThreadOut[]>([]);
  const [activeId, setActiveId] = useState<string | null>(initialRoute.view === "chat" ? initialRoute.threadId : null);
  // 表示中の画面（チャット・文書ライブラリ・ごみ箱）。チャットのスレッドは activeId が持つ
  const [page, setPage] = useState<Route>(initialRoute);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [composerValue, setComposerValue] = useState("");
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [activeCiteTurn, setActiveCiteTurn] = useState(0);
  const [activeSourceId, setActiveSourceId] = useState("");
  const [highlightSectionId, setHighlightSectionId] = useState<string | null>(null);
  const [models, setModels] = useState<ModelOption[] | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [scope, setScope] = useState<ScopeValue>({
    id: "kb:all",
    label: t.chat.scopeAllKbs,
    iconName: "folders",
    desc: t.chat.scopeAllKbsDesc,
    sources: [],
    kbId: null,
  });
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const [awayFromBottom, setAwayFromBottom] = useState(false);

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await chatApi.threads());
    } catch {
      // 一覧の失敗は致命的ではない（次の操作で取り直す）
    }
  }, []);

  const { convs, load, send, cancel, setFeedback, forget } = useConversations({
    onRunEnd: () => void refreshThreads(),
    onThreadCreated: (id) => {
      setActiveId((cur) => (cur === null ? id : cur));
      if (window.location.pathname === "/") window.history.replaceState(null, "", routePath({ view: "chat", threadId: id }));
      void refreshThreads();
    },
  });

  // ── 初期読み込み ────────────────────────────────────────────────────
  useEffect(() => {
    chatApi
      .threads()
      .then(setThreads)
      .catch(() => {});
    chatApi
      .models()
      .then((m) => {
        const opts = m.models.map((x) => ({
          id: x.id,
          label: x.label,
          tag: x.tags[0] ?? "",
          desc: x.tags.join(" · "),
          available: x.available,
        }));
        setModels(opts);
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(MODEL_STORAGE_KEY);
        } catch {}
        const usable = opts.find((o) => o.id === saved && o.available);
        setModelId(usable?.id ?? m.default_id ?? null);
      })
      .catch(() => {
        setModels([]);
        push("モデルの一覧を取得できませんでした", "error");
      });
  }, [push]);

  useEffect(() => {
    chatApi
      .documentStats()
      .then((s) => setStats(normalizeStats(s, kbs.length)))
      .catch(() => setStats(EMPTY_STATS));
  }, [kbs.length]);

  const conv = convs[activeId ?? NEW_THREAD];
  const turns: Turn[] = useMemo(() => conv?.turns ?? [], [conv]);

  // スレッドを開いたら保存済みの内容を読む（生成中なら購読を再開する）
  useEffect(() => {
    if (!activeId || conv?.loaded) return;
    load(activeId).catch(() => {
      push("スレッドを開けませんでした", "error");
      setActiveId(null);
      window.history.replaceState(null, "", "/");
    });
  }, [activeId, conv?.loaded, load, push]);

  // 戻る・進む
  useEffect(() => {
    const onPop = () => {
      const r = parseRoute(window.location.pathname);
      setPage(r);
      if (r.view === "chat") setActiveId(r.threadId);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // ── 表示の状態 ───────────────────────────────────────────────────────
  const lastTurn = turns[turns.length - 1];
  const running = lastTurn?.status === "running";
  const phase: "empty" | "running" | "cancelled" | "done" =
    turns.length === 0 ? "empty" : running ? "running" : lastTurn?.status === "cancelled" ? "cancelled" : "done";
  const activeThread = threads.find((x) => x.id === activeId);
  const title = activeThread?.title ?? turns[0]?.query ?? "";
  const model = models === null ? LOADING_MODEL : (models.find((m) => m.id === modelId) ?? models[0] ?? NO_MODEL);

  // 右パネルは既定で最後のターンを追う
  const lastIdx = turns.length - 1;
  const [syncedKey, setSyncedKey] = useState("");
  const citeKey = `${activeId}:${lastIdx}`;
  if (citeKey !== syncedKey) {
    setSyncedKey(citeKey);
    setActiveCiteTurn(lastIdx < 0 ? 0 : lastIdx);
  }
  const citeTurn = turns[activeCiteTurn] ?? lastTurn;
  const rightPanelShown = rightPanelOpen && phase !== "empty" && page.view === "chat";

  // モバイルに切り替わったらサイドバーを閉じる
  const [wasMobile, setWasMobile] = useState(isMobile);
  if (wasMobile !== isMobile) {
    setWasMobile(isMobile);
    if (isMobile) setSidebarCollapsed(true);
  }

  // 生成中は下に追従する（利用者が上へスクロールしたら止める）
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [turns]);
  const onChatScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    setAwayFromBottom(!stickToBottom.current);
  };
  const jumpToLatest = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = true;
    setAwayFromBottom(false);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  // ── 操作 ─────────────────────────────────────────────────────────────
  const selectThread = (id: string | null) => {
    setActiveId(id);
    setPage({ view: "chat", threadId: id });
    window.history.pushState(null, "", routePath({ view: "chat", threadId: id }));
    setRightPanelOpen(false);
    stickToBottom.current = true;
    setAwayFromBottom(false);
    if (isMobile) setSidebarCollapsed(true);
  };

  const openPage = (r: Route) => {
    setPage(r);
    window.history.pushState(null, "", routePath(r));
    setRightPanelOpen(false);
    if (isMobile) setSidebarCollapsed(true);
  };

  // ライブラリから「この KB に質問」: 検索範囲をその KB にして新しいスレッドへ
  const askInKb = (kbId: string | null) => {
    const kb = kbId ? kbs.find((k) => k.id === kbId) : undefined;
    setScope(
      kb
        ? {
            id: `kb:${kb.id}`,
            label: kb.kind === "personal" ? t.chat.scopePersonalKb : kb.name,
            iconName: kb.kind === "personal" ? "user" : "database",
            sources: [],
            kbId: kb.id,
          }
        : { id: "kb:all", label: t.chat.scopeAllKbs, iconName: "folders", desc: t.chat.scopeAllKbsDesc, sources: [], kbId: null },
    );
    selectThread(null);
  };

  const runBody = () => ({
    model_id: modelId,
    kb_ids: scope.kbId ? [scope.kbId] : null,
    include_archived: Boolean(scope.includeArchived),
  });

  const startRun = (query: string) => {
    const q = query.trim();
    if (!q || running) return;
    setComposerValue("");
    stickToBottom.current = true;
    void send(activeId, q, { body: runBody() });
  };

  /** idx のターンを作り直す（同じ質問 = 再生成、別の質問 = 編集）。 */
  const rerun = (idx: number, query?: string) => {
    if (running) {
      push(t.feedback.regenerateBlocked, "info");
      return;
    }
    const turn = turns[idx];
    if (!turn || !activeId) return;
    // 保存済みのメッセージがあればそこから分岐、無ければ（受付前に取り消した等）新しい質問として送る
    void send(activeId, query ?? turn.query, {
      fromIdx: idx,
      fromMessageId: turn.messageId ?? null,
      body: runBody(),
    });
    if (!query) push(t.feedback.regenerating, "info");
  };

  const stopRun = () => {
    const runId = lastTurn?.runId;
    if (!runId || runId.startsWith("pending:")) return;
    cancel(runId).catch(() => push(t.feedback.runFailed, "error"));
  };

  const openCitation = (n: number, idx: number) => {
    const c = turns[idx]?.citationMap[n];
    if (!c) return;
    setActiveCiteTurn(idx);
    setActiveSourceId(c.sourceId);
    setHighlightSectionId(c.sectionId);
    setRightPanelOpen(true);
  };

  const openSourcesForTurn = (idx: number) => {
    setActiveCiteTurn(idx);
    setActiveSourceId(turns[idx]?.sources[0]?.id ?? "");
    setHighlightSectionId(null);
    setRightPanelOpen(true);
  };

  const copyAnswer = async (idx: number) => {
    try {
      const text = (turns[idx]?.answer ?? "").replace(/\*\*/g, "").replace(/\[\d+\]/g, "");
      await navigator.clipboard.writeText(text);
      push(t.feedback.answerCopied, "success");
    } catch {
      push(t.feedback.copyFailed, "error");
    }
  };

  const downloadAnswer = (idx: number) => {
    const turn = turns[idx];
    if (!turn?.answer) return;
    const base = (turn.query || "answer").trim().slice(0, 40).replace(/[\\/:*?"<>|]/g, "_") || "answer";
    const url = URL.createObjectURL(new Blob([turn.answer], { type: "text/markdown;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${base}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const applyFeedback = async (idx: number, fb: TurnFeedback) => {
    const turn = turns[idx];
    if (!activeId || !turn?.messageId) return;
    const prev = turn.feedback ?? null;
    setFeedback(activeId, idx, fb);
    try {
      await chatApi.feedback(turn.messageId, { rating: fb.rating, reason_tags: fb.reasonTags, comment: fb.comment });
      push(fb.rating === "down" ? t.feedback.feedbackImprovement : t.feedback.feedbackSent, "success");
    } catch {
      setFeedback(activeId, idx, prev);
      push(t.feedback.feedbackFailed, "error");
    }
  };
  const onFeedbackToggle = (v: FeedbackRating, idx: number) => {
    if (v === "up") void applyFeedback(idx, { rating: "up", reasonTags: [], comment: null });
  };
  const onFeedbackDetail = (v: { reasonTags: FeedbackReasonTag[]; comment: string }, idx: number) => {
    void applyFeedback(idx, { rating: "down", reasonTags: v.reasonTags, comment: v.comment.trim() || null });
  };

  const renameThread = async (id: string, title: string) => {
    const prev = threads;
    setThreads((cur) => cur.map((x) => (x.id === id ? { ...x, title } : x)));
    try {
      await chatApi.patchThread(id, { title });
      push(t.feedback.threadRenamed, "success");
    } catch {
      setThreads(prev);
      push(t.feedback.threadRenameFailed, "error");
    }
  };

  const toggleStar = async (id: string, pinned: boolean) => {
    const prev = threads;
    setThreads((cur) => cur.map((x) => (x.id === id ? { ...x, pinned } : x)));
    try {
      await chatApi.patchThread(id, { pinned });
      push(pinned ? t.feedback.starAdded : t.feedback.starRemoved, "success");
      void refreshThreads();
    } catch {
      setThreads(prev);
      push(t.feedback.starUpdateFailed, "error");
    }
  };

  const deleteThread = async (id: string) => {
    const target = threads.find((x) => x.id === id);
    const ok = await confirm({
      title: t.workspace.deleteThreadTitle,
      description: target
        ? interpolate(t.workspace.deleteThreadDescWithTitle, { title: target.title })
        : t.workspace.deleteThreadDescGeneric,
      confirmLabel: t.workspace.deleteThreadConfirm,
      cancelLabel: t.workspace.deleteThreadCancel,
      tone: "danger",
    });
    if (!ok) return;
    try {
      await chatApi.deleteThread(id);
      setThreads((cur) => cur.filter((x) => x.id !== id));
      forget(id);
      if (activeId === id) selectThread(null);
      push(t.feedback.threadDeleted, "success");
    } catch {
      push(t.feedback.threadDeleteFailed, "error");
    }
  };

  const onPanelAction = (kind: RightPanelAction, src: Source) => {
    if (kind === "open-source") {
      const w = window.open(originalUrl(src.id), "_blank", "noopener");
      if (!w) push(t.feedback.popupBlocked, "error");
    } else if (kind === "download") {
      const a = document.createElement("a");
      a.href = originalUrl(src.id);
      a.download = src.title;
      a.click();
      push(interpolate(t.feedback.sourceDownloaded, { filename: src.title }), "success");
    }
  };

  // キーボード操作（Esc で右パネルを閉じる、⇧⌘O 新規、⌘B サイドバー、⌘⌫ 停止）。
  // 最新の状態を見るため、登録は 1 回にして処理は ref から呼ぶ
  const onKeyRef = useRef<(e: KeyboardEvent) => void>(() => {});
  useEffect(() => {
    onKeyRef.current = (e) => {
      if (e.key === "Escape" && rightPanelOpen) {
        setRightPanelOpen(false);
        return;
      }
      const action = shortcutAction(e, { running });
      if (!action) return;
      e.preventDefault();
      if (action === "new-thread") {
        selectThread(null);
        setComposerValue("");
      } else if (action === "toggle-sidebar") setSidebarCollapsed((c) => !c);
      else stopRun();
    };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => onKeyRef.current(e);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ── 描画 ─────────────────────────────────────────────────────────────
  const threadList: ThreadSummary[] = threads.map((th) => ({
    ...toSummary(th),
    running: convs[th.id]?.turns.at(-1)?.status === "running",
  }));
  const backdropVisible = isWide ? false : isMobile ? !sidebarCollapsed || rightPanelShown : rightPanelShown;

  return (
    <>
      <AppShell
        sidebarCollapsed={sidebarCollapsed}
        rightPanelShown={rightPanelShown}
        panelWidth={panelWidth}
        compact={tweaks.density === "compact"}
        backdropVisible={backdropVisible}
        onBackdropClick={() => {
          setSidebarCollapsed(true);
          setRightPanelOpen(false);
        }}
        sidebar={
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed((c) => !c)}
            threads={threadList}
            activeThreadId={page.view === "chat" ? (activeId ?? "") : ""}
            onOpenLibrary={(kbId) => openPage({ view: "library", kbId })}
            onOpenTrash={() => openPage({ view: "trash" })}
            activeKbId={page.view === "library" ? page.kbId : undefined}
            trashActive={page.view === "trash"}
            onSelectThread={(id) => selectThread(id)}
            onNewChat={() => {
              selectThread(null);
              setComposerValue("");
            }}
            onToggleTheme={() => setTweak("dark", !tweaks.dark)}
            onRenameThread={renameThread}
            onDeleteThread={deleteThread}
            onToggleStar={toggleStar}
            dataSourceCount={stats?.totalDocumentCount ?? 0}
            dark={tweaks.dark}
            user={DEV_USER}
          />
        }
        rightPanel={
          rightPanelShown ? (
            <RightPanel
              sources={citeTurn?.sources ?? []}
              contextQuery={citeTurn?.query}
              citationMap={citeTurn?.citationMap ?? {}}
              activeSourceId={activeSourceId}
              highlightSectionId={highlightSectionId}
              onSetActive={(id) => {
                setActiveSourceId(id);
                setHighlightSectionId(null);
              }}
              onClose={() => setRightPanelOpen(false)}
              resizable={isWide}
              panelWidth={panelWidth}
              onResizeWidth={handleResizeWidth}
              onAction={onPanelAction}
            />
          ) : null
        }
      >
        {page.view === "library" ? (
          <LibraryView kbId={page.kbId} onAsk={askInKb} onOpenMenu={() => setSidebarCollapsed(false)} />
        ) : page.view === "trash" ? (
          <TrashView onOpenMenu={() => setSidebarCollapsed(false)} />
        ) : (
        <main className="grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] overflow-hidden bg-bg">
          <header className="sticky top-0 z-[5] flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider bg-bg px-[18px] max-md:gap-1 max-md:px-2.5">
            <button
              className="-ml-1 hidden h-[34px] w-[34px] shrink-0 place-items-center rounded-lg border-0 bg-transparent text-fg hover:bg-divider max-md:grid"
              onClick={() => setSidebarCollapsed(false)}
              aria-label={t.workspace.openMenuAriaLabel}
            >
              <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden>
                <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
            <div className="flex min-w-0 flex-1 items-center gap-2 text-[13.5px] font-semibold text-fg max-md:gap-1.5 max-md:text-[13px]">
              {phase === "empty" ? (
                <span className="font-medium text-muted">
                  {activeId ? (activeThread?.title ?? "") : t.workspace.headerNewThread}
                </span>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate">{title.slice(0, 80) || t.workspace.headerThreadFallback}</span>
                  {phase === "cancelled" && (
                    <span className="ml-1.5 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-danger-soft px-[7px] py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.04em] text-danger">
                      {t.workspace.badgeCancelled}
                    </span>
                  )}
                  {phase === "running" && (
                    <span className="ml-1.5 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-accent-soft px-[7px] py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.04em] text-accent before:h-[5px] before:w-[5px] before:rounded-full before:bg-accent before:[animation:ar-pulse_1.2s_ease-in-out_infinite]">
                      {conv?.reconnecting ? t.chat.reconnecting : t.workspace.badgeRunning}
                    </span>
                  )}
                </>
              )}
            </div>
            <div className="flex items-center gap-1.5 max-md:gap-0.5">
              {phase !== "empty" && !rightPanelOpen && (citeTurn?.sources.length ?? 0) > 0 && (
                <button
                  className="inline-flex h-[30px] items-center gap-1.5 rounded-lg border border-accent bg-transparent px-2.5 text-[12px] font-medium text-accent hover:bg-accent-soft max-md:h-8 max-md:px-2.5 max-md:text-[11.5px]"
                  onClick={() => openSourcesForTurn(activeCiteTurn)}
                >
                  <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
                    <path d="M3 3h10v10H3z" stroke="currentColor" strokeWidth="1.4" fill="none" />
                    <path d="M10 3v10" stroke="currentColor" strokeWidth="1.4" />
                  </svg>
                  {interpolate(t.workspace.btnSources, { n: String(citeTurn?.sources.length ?? 0) })}
                </button>
              )}
              <ThemeToggle dark={tweaks.dark} onToggle={() => setTweak("dark", !tweaks.dark)} />
            </div>
          </header>

          <div className="relative grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[1fr_auto] overflow-hidden">
            <div ref={scrollRef} onScroll={onChatScroll} className="overflow-x-hidden overflow-y-auto">
              {phase === "empty" ? (
                activeId && !conv?.loaded ? (
                  <div className="grid h-full place-items-center">
                    <span className="h-6 w-6 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
                  </div>
                ) : (
                  <EmptyState user={DEV_USER} stats={stats} onFillComposer={(v) => setComposerValue(v)} />
                )
              ) : (
                <div
                  className={cn(
                    "mx-auto flex max-w-[1020px] flex-col gap-6 px-8 pb-[60px] pt-7 max-md:max-w-none max-md:gap-[18px] max-md:px-3.5 max-md:pb-20 max-md:pt-[18px]",
                    tweaks.density === "compact" && "gap-4 px-5 pb-10 pt-[18px]",
                  )}
                >
                  <Transcript
                    turns={turns}
                    toolView={tweaks.toolView}
                    expandedSteps={expandedSteps}
                    onToggleStep={(id) => setExpandedSteps((m) => ({ ...m, [id]: !m[id] }))}
                    onCite={openCitation}
                    citationStyle={tweaks.citationStyle}
                    onCopy={copyAnswer}
                    onDownload={downloadAnswer}
                    onDownloadHtml={downloadAnswer}
                    onRegenerate={(idx) => rerun(idx)}
                    onEdit={running ? undefined : (idx, text) => rerun(idx, text)}
                    onOpenSources={openSourcesForTurn}
                    onFeedback={onFeedbackToggle}
                    onFeedbackDetail={onFeedbackDetail}
                    feedback={{}}
                    activeCiteTurn={activeCiteTurn}
                    rightPanelOpen={rightPanelShown}
                    liveAttachments={[]}
                    isLiveLastTurn={false}
                  />
                </div>
              )}
            </div>

            {awayFromBottom && phase !== "empty" && (
              <div className="pointer-events-none relative h-0">
                <button
                  type="button"
                  onClick={jumpToLatest}
                  className="pointer-events-auto absolute -top-12 left-1/2 z-10 inline-flex h-8 -translate-x-1/2 items-center gap-1.5 rounded-full border-[0.5px] border-divider-strong bg-surface px-3 text-[12px] font-medium text-fg shadow-e2 hover:bg-surface-2"
                >
                  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden>
                    <path d="M8 3v10M8 13l-4-4M8 13l4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {running ? "生成中の回答へ" : "最新へ"}
                </button>
              </div>
            )}
            <Composer
              value={composerValue}
              onChange={setComposerValue}
              onSubmit={() => startRun(composerValue)}
              onStop={stopRun}
              model={model}
              models={models ?? []}
              onSelectModel={(m) => {
                setModelId(m.id);
                try {
                  localStorage.setItem(MODEL_STORAGE_KEY, m.id);
                } catch {}
                push(interpolate(t.feedback.modelSwitched, { label: m.label }), "success");
              }}
              running={running}
              scope={scope}
              onChangeScope={(s) => {
                setScope(s);
                push(interpolate(t.feedback.scopeChanged, { label: s.label }), "info");
              }}
            />
          </div>
        </main>
        )}
      </AppShell>
      {confirmDialog}
    </>
  );
}
