"use client";

/** チャット画面（specs/005-agent D4〜D6）。画面の切り替え・会話・右パネル・ダイアログをまとめる。
 *
 * - URL は `/`（新規）と `/c/<threadId>`、ライブラリ・ごみ箱。切り替えは history.pushState で行い、画面は再マウントしない
 *   （生成中の run の購読を保つため）。再読み込みすると active-run から続きを表示する。
 * - 状態ごとの処理は chat/app/ に分けてある: スレッド use-threads・モデル use-models・スクロール use-chat-scroll・
 *   回答への操作 use-answer-actions・初回ガイド use-guide・上部バー chat-header・「最新へ」jump-to-latest。
 */
import { TranscriptSkeleton } from "@/components/ui/skeleton";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { Sidebar } from "@/components/sidebar/sidebar";
import { LibraryView } from "@/components/library/library-view";
import { TrashView } from "@/components/library/trash-view";
import { DocumentViewer } from "@/components/library/document-viewer";
import { ShareDialog } from "@/components/chat/share-dialog";
import { ChatHeader } from "@/components/chat/app/chat-header";
import { JumpToLatest } from "@/components/chat/app/jump-to-latest";
import { useAnswerActions } from "@/components/chat/app/use-answer-actions";
import { useChatScroll } from "@/components/chat/app/use-chat-scroll";
import { useGuide } from "@/components/chat/app/use-guide";
import { useModels } from "@/components/chat/app/use-models";
import { toSummary, useThreads } from "@/components/chat/app/use-threads";
import { libraryApi, type DocumentOut } from "@/lib/library/api";
import { kbLabel } from "@/lib/library/view";
import { parseRoute, routePath, type Route } from "@/lib/routes";
import { UnverifiedBanner } from "@/components/auth/unverified-banner";
import { authClient } from "@/lib/auth/client";
import { toAppUser } from "@/lib/auth/user";
import { Composer } from "@/components/chat/composer";
import { HomeHero, HomeSuggestions } from "@/components/chat/empty-state";
import { Transcript } from "@/components/chat/messages";
import { RightPanel, type RightPanelAction } from "@/components/sources/right-panel";
import { originalUrl } from "@/components/documents/original-preview";
import { useToast } from "@/components/feedback/toast-provider";
import { useConversations, NEW_THREAD } from "@/hooks/use-conversations";
import { useKbs } from "@/hooks/use-kbs";
import { useMediaQuery } from "@/hooks/use-media-query";
import { HelpModal } from "@/components/help/help-modal";
import { OnboardingTour } from "@/components/onboarding/onboarding-tour";
import { SettingsModal } from "@/components/settings/settings-modal";
import { useAgentCfg } from "@/hooks/use-agent-cfg";
import { useTweaks } from "@/hooks/use-tweaks";
import { usePanelWidth } from "@/components/workspace/use-panel-width";
import { chatApi } from "@/lib/chat/api";
import { agentCfgPayload } from "@/lib/agent-settings";
import { isEditable, shortcutAction } from "@/lib/shortcuts";
import type { AppUser, ScopeValue, Source, ThreadSummary, Turn } from "@/lib/types";
import { cn } from "@/lib/utils";
import { checkImageFile, imageFromUrl, shrinkImage, type QueryImage } from "@/lib/query-image";
import { EMPTY_STATS, normalizeStats, type WorkspaceStats } from "@/lib/workspace-stats";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { AnimatePresence, m } from "motion/react";
import { CommandPalette, type PaletteItem } from "@/components/command-palette";
import { AmbientGlow } from "@/components/ambient-glow";
import { kbGlyph } from "@/lib/home";
import { SHORTCUT_LABEL } from "@/lib/shortcuts";

// 認証を使わない開発構成（ARAG_DEV_USER_ID）のときの表示用の利用者
const DEV_USER: AppUser = {
  name: "開発ユーザー",
  firstName: "開発ユーザー",
  org: "ARag",
  initials: "開",
  email: "dev@example.com",
  onboardedAt: null,
  emailVerifiedAt: null,
};

export function ChatApp({ initialRoute }: { initialRoute: Route }) {
  const { t } = useT();
  const push = useToast();
  const { tweaks, setTweak } = useTweaks();
  const { cfg: agentCfg } = useAgentCfg();
  const { kbs } = useKbs();
  const { data: session } = authClient.useSession();
  const sessionUser = session?.user;
  const user = useMemo(() => (sessionUser ? toAppUser(sessionUser) : DEV_USER), [sessionUser]);
  const isAdmin = sessionUser?.role === "owner" || sessionUser?.role === "admin";
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const router = useRouter();

  // メール確認リンクから戻ってきたとき（?verified=1 / ?error=...）に知らせて、URL から消す
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (!q.has("verified") && !q.has("error")) return;
    if (q.has("error")) push("確認リンクが無効か、期限が切れています。確認メールを再送してください", "error");
    else push("メールアドレスを確認しました。質問と文書の追加ができます", "success");
    window.history.replaceState(null, "", window.location.pathname);
  }, [push]);

  const signOut = async () => {
    await authClient.signOut();
    router.replace("/login");
  };
  const [panelWidth, handleResizeWidth] = usePanelWidth();
  const isMobile = useMediaQuery("(max-width: 768px)");
  const isWide = useMediaQuery("(min-width: 1181px)");


  const [activeId, setActiveId] = useState<string | null>(initialRoute.view === "chat" ? initialRoute.threadId : null);
  // 表示中の画面（チャット・文書ライブラリ・ごみ箱）。チャットのスレッドは activeId が持つ
  const [page, setPage] = useState<Route>(initialRoute);
  const guide = useGuide(sessionUser?.id ?? null, page.view === "chat");
  /** ライブラリの上に重ねる文書ビューア。開くときに同じ URL の履歴を 1 つ積み、戻るボタンで閉じる。 */
  const [viewerDoc, setViewerDoc] = useState<DocumentOut | null>(null);
  /** 回答の出典から「対照」を開くとき、選んでおく章（specs/030 R13） */
  const [viewerSectionId, setViewerSectionId] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [composerFocus, setComposerFocus] = useState(0);
  // ⌘K の候補。開いた時点の一覧を持つ（null = 閉じている）
  const [palette, setPalette] = useState<PaletteItem[] | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [composerValue, setComposerValue] = useState("");
  // 質問に添える画像（specs/017）。imageInput（use-models）は API が図の説明用モデルを持つときだけ true
  const [queryImage, setQueryImage] = useState<QueryImage | null>(null);
  const [imageBusy, setImageBusy] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [activeCiteTurn, setActiveCiteTurn] = useState(0);
  const [activeSourceId, setActiveSourceId] = useState("");
  const [highlightSectionId, setHighlightSectionId] = useState<string | null>(null);
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [scope, setScope] = useState<ScopeValue>({
    id: "kb:all",
    label: t.chat.scopeAllKbs,
    iconName: "folders",
    desc: t.chat.scopeAllKbsDesc,
    sources: [],
    kbId: null,
  });
  const { models, model, modelId, modelLoading, imageInput, selectModel } = useModels();
  const { threads, refreshThreads, renameThread, toggleStar, deleteThread, replaceThread, confirmDialog } = useThreads({
    onDeleted: (id) => {
      forget(id);
      if (activeId === id) selectThread(null);
    },
  });

  const { convs, load, send, cancel, setFeedback, markUnsaved, forget } = useConversations({
    onRunEnd: () => void refreshThreads(),
    onThreadCreated: (id) => {
      setActiveId((cur) => (cur === null ? id : cur));
      if (window.location.pathname === "/") window.history.replaceState(null, "", routePath({ view: "chat", threadId: id }));
      void refreshThreads();
    },
  });

  useEffect(() => {
    chatApi
      .documentStats()
      .then((s) => setStats(normalizeStats(s, kbs.length)))
      .catch(() => setStats(EMPTY_STATS));
  }, [kbs.length]);

  const conv = convs[activeId ?? NEW_THREAD];
  const turns: Turn[] = useMemo(() => conv?.turns ?? [], [conv]);
  const { scrollRef, onScroll, awayFromBottom, scrolled, jumpToLatest, stick, reset: resetScroll } = useChatScroll(turns);
  const answer = useAnswerActions({ turns, threadId: activeId, setFeedback, markUnsaved });

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
      setViewerDoc(null);
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
  // 首ページ: スレッドが空で、開こうとしているスレッドの読み込み中でもないとき
  const home = phase === "empty" && !(activeId && !conv?.loaded);

  // モバイルに切り替わったらサイドバーを閉じる
  const [wasMobile, setWasMobile] = useState(isMobile);
  if (wasMobile !== isMobile) {
    setWasMobile(isMobile);
    if (isMobile) setSidebarCollapsed(true);
  }

  // ── 操作 ─────────────────────────────────────────────────────────────
  const selectThread = (id: string | null) => {
    setActiveId(id);
    setPage({ view: "chat", threadId: id });
    window.history.pushState(null, "", routePath({ view: "chat", threadId: id }));
    setRightPanelOpen(false);
    resetScroll();
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
    setComposerFocus((n) => n + 1);
  };

  const openDocument = (d: DocumentOut, sectionId: string | null = null) => {
    setViewerSectionId(sectionId);
    setViewerDoc(d);
    window.history.pushState({ viewer: d.id }, "", window.location.pathname);
  };
  const closeDocument = () => {
    if ((window.history.state as { viewer?: string } | null)?.viewer) window.history.back();
    else setViewerDoc(null);
  };
  // 文書ビューアから「この文書に質問」: 検索範囲をその文書だけにして新しいスレッドへ
  const askInDocument = (d: DocumentOut) => {
    setScope({ id: `doc:${d.id}`, label: d.filename, iconName: "doc", sources: [], kbId: d.kb_id, documentIds: [d.id] });
    setViewerDoc(null);
    selectThread(null);
    setComposerFocus((n) => n + 1);
  };

  const runBody = () => ({
    model_id: modelId,
    kb_ids: scope.kbId ? [scope.kbId] : null,
    document_ids: scope.documentIds?.length ? scope.documentIds : null,
    include_archived: Boolean(scope.includeArchived),
    // 既定から変えた回答の設定だけ（specs/014-settings R4）
    agent_cfg: agentCfgPayload(agentCfg),
  });

  const pickImage = async (f: File) => {
    const err = checkImageFile(f);
    if (err) {
      push(err, "error");
      return;
    }
    setImageBusy(true);
    try {
      setQueryImage(await shrinkImage(f));
    } catch {
      push(t.chat.imageReadFailed, "error");
    } finally {
      setImageBusy(false);
    }
  };

  const startRun = (query: string) => {
    const q = query.trim();
    const img = queryImage;
    if ((!q && !img) || running || imageBusy) return;
    setComposerValue("");
    setQueryImage(null);
    stick();
    // 画像だけのときは API が既定の質問を入れる。表示用にもここで同じ文言を使う
    void send(activeId, q || t.chat.imageDefaultQuery, {
      body: { ...runBody(), image: img ? { data: img.dataUrl } : null },
      image: img ? { url: img.dataUrl, width: img.width, height: img.height } : undefined,
    });
  };

  /** 続けて聞く候補を押したら、その文をそのまま送る。入力欄の下書きと画像には触れない（specs/028）。 */
  const askFollowup = (text: string) => {
    if (running || imageBusy) return;
    stick();
    void send(activeId, text, { body: { ...runBody(), image: null } });
  };

  /** idx のターンを作り直す（同じ質問 = 再生成、別の質問 = 編集）。 */
  const rerun = (idx: number, query?: string) => {
    if (running) {
      push(t.feedback.regenerateBlocked, "info");
      return;
    }
    const turn = turns[idx];
    if (!turn || !activeId) return;
    stick();
    // 保存済みのメッセージがあればそこから分岐、無ければ（受付前に取り消した等）新しい質問として送る。
    // 画像つきのターンは同じ画像を送り直す（読み取りは作り直しのたびに行う）
    const go = (img: QueryImage | null) =>
      void send(activeId, query ?? turn.query, {
        fromIdx: idx,
        fromMessageId: turn.messageId ?? null,
        body: { ...runBody(), image: img ? { data: img.dataUrl } : null },
        image: img ? { url: img.dataUrl, width: img.width, height: img.height } : undefined,
      });
    if (turn.image) {
      imageFromUrl(turn.image.url)
        .then(go)
        .catch(() => {
          push(t.chat.imageReadFailed, "error");
          go(null);
        });
    } else go(null);
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

  const onPanelAction = (kind: RightPanelAction, src: Source, sectionId?: string | null) => {
    if (kind === "inspect") {
      libraryApi.document(src.id).then(
        (d) => openDocument(d, sectionId ?? null),
        () => push(t.feedback.documentOpenFailed, "error"),
      );
    } else if (kind === "open-source") {
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
  /** ⌘K の候補: 操作 → ナレッジベース → スレッド（開く操作の中で、今の一覧から作る） */
  const paletteItems = (): PaletteItem[] => {
    return [
      { id: "new", group: "操作", label: "新しいスレッド", icon: "plus", hint: SHORTCUT_LABEL.newThread, run: () => { selectThread(null); setComposerValue(""); } },
      { id: "library", group: "操作", label: "すべての文書を開く", icon: "database", run: () => openPage({ view: "library", kbId: null }) },
      { id: "theme", group: "操作", label: tweaks.dark ? "ライトモードにする" : "ダークモードにする", icon: tweaks.dark ? "sun" : "moon", run: () => setTweak("dark", !tweaks.dark) },
      { id: "settings", group: "操作", label: "設定を開く", icon: "cog", hint: SHORTCUT_LABEL.settings, run: () => setSettingsOpen(true) },
      { id: "help", group: "操作", label: "ヘルプを開く", icon: "info", hint: SHORTCUT_LABEL.help, run: () => setHelpOpen(true) },
      ...(isAdmin ? [{ id: "admin", group: "操作", label: "管理コンソールを開く", icon: "shield" as const, run: () => router.push("/admin/members") }] : []),
      ...kbs.map((kb) => ({
        id: `kb-${kb.id}`,
        group: "ナレッジベース",
        label: kbLabel(kb),
        ...(kb.kind === "personal" ? { icon: "user" as const } : { glyph: kbGlyph(kb.name) }),
        run: () => openPage({ view: "library", kbId: kb.id }),
      })),
      ...threads.map((th) => ({ id: `th-${th.id}`, group: "スレッド", label: toSummary(th).title, icon: "chat" as const, run: () => selectThread(th.id) })),
    ];
  };

  const onKeyRef = useRef<(e: KeyboardEvent) => void>(() => {});
  useEffect(() => {
    onKeyRef.current = (e) => {
      if (settingsOpen || helpOpen || guide.open) return; // ダイアログの中ではキーを奪わない
      if (e.key === "Escape" && rightPanelOpen) {
        setRightPanelOpen(false);
        return;
      }
      const action = shortcutAction(e, { running, editing: isEditable(e.target) });
      if (!action) return;
      e.preventDefault();
      if (action === "new-thread") {
        selectThread(null);
        setComposerValue("");
      } else if (action === "toggle-sidebar") setSidebarCollapsed((c) => !c);
      else if (action === "open-settings") setSettingsOpen(true);
      else if (action === "open-help") setHelpOpen(true);
      else if (action === "command-palette") setPalette((p) => (p ? null : paletteItems()));
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
            user={user}
            onSignOut={sessionUser ? () => void signOut() : undefined}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenHelp={() => setHelpOpen(true)}
            onOpenPalette={() => setPalette(paletteItems())}
            onOpenAdmin={isAdmin ? () => router.push("/admin/members") : undefined}
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
        <div className="grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
        {sessionUser && !sessionUser.emailVerified ? <UnverifiedBanner email={sessionUser.email} /> : <div />}
        {page.view === "library" ? (
          <LibraryView
            kbId={page.kbId}
            folderId={page.folderId ?? null}
            onOpenFolder={(folderId) => openPage({ view: "library", kbId: page.kbId, folderId })}
            onAsk={askInKb}
            onOpenDocument={openDocument}
            onOpenMenu={() => setSidebarCollapsed(false)}
          />
        ) : page.view === "trash" ? (
          <TrashView onOpenMenu={() => setSidebarCollapsed(false)} />
        ) : (
        <main
          className={cn(
            "grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] overflow-hidden bg-bg",
            // 首ページでは地を透かして、後ろで漂う光（AmbientGlow）を見せる
            home && "bg-transparent",
          )}
        >
          {/* 首ページの後ろでゆっくり漂う光。サイドバーの下まで広げ、半透明のサイドバー越しにも見せる */}
          {home && <AmbientGlow className="fixed inset-0 -z-10" />}
          <ChatHeader
            phase={phase}
            home={home}
            scrolled={scrolled}
            title={title}
            emptyTitle={activeId ? (activeThread?.title ?? "") : null}
            reconnecting={Boolean(conv?.reconnecting)}
            sourceCount={rightPanelOpen ? 0 : (citeTurn?.sources.length ?? 0)}
            shared={Boolean(activeThread?.visibility && activeThread.visibility !== "private")}
            canShare={Boolean(activeThread)}
            dark={tweaks.dark}
            onOpenMenu={() => setSidebarCollapsed(false)}
            onOpenSources={() => openSourcesForTurn(activeCiteTurn)}
            onShare={() => setShareOpen(true)}
            onToggleTheme={() => setTweak("dark", !tweaks.dark)}
          />


          {/* 首ページ（home）は 挨拶 / 入力欄 / 質問の候補 の 3 段で入力欄を中央に置く（specs/025 R44）。
              狭い画面では挨拶のすぐ下に入力欄を置く（キーボードに隠れない）。会話になると入力欄は下端へ滑る。 */}
          <div
            className={cn(
              "relative grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] overflow-hidden",
              home
                ? "grid-rows-[minmax(0,1fr)_auto_minmax(0,1.2fr)] max-md:grid-rows-[auto_auto_minmax(0,1fr)]"
                : "grid-rows-[1fr_auto]",
            )}
          >
            <div
              ref={scrollRef}
              onScroll={onScroll}
              className={cn("overflow-x-hidden overflow-y-auto", home && "flex items-end justify-center")}
            >
              {phase === "empty" ? (
                activeId && !conv?.loaded ? (
                  <TranscriptSkeleton />
                ) : (
                  <HomeHero user={user} />
                )
              ) : (
                <div
                  // スレッドを切り替えたら、中身を短く淡く出す（specs/025 R30）
                  key={activeId ?? "new"}
                  className={cn(
                    "mx-auto flex max-w-[1020px] animate-fade-in flex-col gap-6 px-8 pb-[60px] pt-7 motion-reduce:animate-none max-md:max-w-none max-md:gap-[18px] max-md:px-3.5 max-md:pb-20 max-md:pt-[18px]",
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
                    onCopy={answer.copy}
                    onDownload={answer.download}
                    onDownloadHtml={(idx) => void answer.downloadHtml(idx)}
                    onRegenerate={(idx) => rerun(idx)}
                    onEdit={running ? undefined : (idx, text) => rerun(idx, text)}
                    onFollowup={running ? undefined : askFollowup}
                    onFeedback={answer.onFeedback}
                    onFeedbackDetail={answer.onFeedbackDetail}
                    feedback={{}}
                    liveAttachments={[]}
                    isLiveLastTurn={false}
                  />
                </div>
              )}
            </div>

            <JumpToLatest visible={awayFromBottom && phase !== "empty"} running={running} onJump={jumpToLatest} />

            <m.div layout="position" className={cn("min-w-0", home && "mx-auto w-full max-w-[760px]")}>
            <Composer
              value={composerValue}
              onChange={setComposerValue}
              onSubmit={() => startRun(composerValue)}
              onStop={stopRun}
              model={model}
              models={models}
              onSelectModel={selectModel}
              modelLoading={modelLoading}
              running={running}
              scope={scope}
              focusKey={composerFocus}
              quiet={home}
              image={queryImage}
              imageBusy={imageBusy}
              onPickImage={imageInput ? (f) => void pickImage(f) : undefined}
              onRemoveImage={() => setQueryImage(null)}
              onChangeScope={(s) => {
                setScope(s);
                push(interpolate(t.feedback.scopeChanged, { label: s.label }), "info");
              }}
            />
            </m.div>
            {home && (
              <div className="min-h-0 overflow-y-auto">
                <HomeSuggestions
                  stats={stats}
                  onFillComposer={(v) => {
                    setComposerValue(v);
                    setComposerFocus((k) => k + 1);
                  }}
                />
              </div>
            )}
          </div>
        </main>
        )}
        </div>
      </AppShell>
      {confirmDialog}
      {palette && <CommandPalette items={palette} onClose={() => setPalette(null)} />}
      {helpOpen && (
        <HelpModal
          onClose={() => setHelpOpen(false)}
          stats={stats}
          onReplayTour={() => {
            setHelpOpen(false);
            // ガイドは会話の画面の部品（入力欄・検索の範囲）を指すので、ライブラリ等からは新しいスレッドへ移ってから始める
            if (page.view !== "chat") selectThread(null);
            guide.replay();
          }}
        />
      )}
      <AnimatePresence>{guide.open && <OnboardingTour key="tour" name={sessionUser?.name} onClose={guide.close} />}</AnimatePresence>
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} showAccount={Boolean(sessionUser)} />}
      {shareOpen && activeThread && (
        <ShareDialog
          thread={activeThread}
          onChange={replaceThread}
          onClose={() => setShareOpen(false)}
        />
      )}
      <AnimatePresence>
      {viewerDoc && (
        <DocumentViewer
          key={viewerDoc.id}
          doc={viewerDoc}
          kbName={(() => {
            const kb = kbs.find((k) => k.id === viewerDoc.kb_id);
            return kb ? kbLabel(kb) : "";
          })()}
          onClose={closeDocument}
          onAsk={askInDocument}
          isAdmin={isAdmin}
          initialSectionId={viewerSectionId}
        />
      )}
      </AnimatePresence>
    </>
  );
}
