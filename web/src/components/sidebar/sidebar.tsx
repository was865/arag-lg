"use client";

import { SHORTCUT_LABEL } from "@/lib/shortcuts";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { kbGlyph } from "@/lib/home";
import { IconButton } from "@/components/ui/button";
import { SidebarHeader } from "@/components/sidebar/sidebar-header";
import { SidebarNewButton } from "@/components/sidebar/sidebar-new-button";
import { SidebarRail, SidebarRailButton } from "@/components/sidebar/sidebar-rail";
import { SidebarUserFooter } from "@/components/sidebar/sidebar-footer";
import { ThreadRow, ThreadMenuItems } from "@/components/sidebar/thread-item";
import { SidebarSearchResults } from "@/components/sidebar/sidebar-search-results";
import { useThreadSearch } from "@/hooks/use-thread-search";
import { cn } from "@/lib/utils";
import type { AppUser, ThreadSummary } from "@/lib/types";
import { refreshKbs, useKbs } from "@/hooks/use-kbs";
import { useDepartments } from "@/hooks/use-departments";
import { CreateKbDialog } from "@/components/access/create-kb-dialog";
import { useT } from "@/i18n/context";
import { Badge } from "@/components/ui/badge";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  threads: ThreadSummary[];
  activeThreadId: string;
  onSelectThread: (id: string) => void;
  onNewChat: () => void;
  onOpenSettings?: () => void;
  /** org admin のときだけ渡される（未指定ならメニューに出さない）。 */
  onOpenAdmin?: () => void;
  /** 只読工作日历を開く（未指定ならメニューに出さない）。 */
  onOpenWorkCalendar?: () => void;
  onOpenHelp?: () => void;
  /** ⌘K のコマンドパレットを開く */
  onOpenPalette?: () => void;
  onSignOut?: () => void;
  onToggleTheme: () => void;
  onRenameThread: (id: string, title: string) => void | Promise<void>;
  onDeleteThread: (id: string) => void | Promise<void>;
  onToggleStar: (id: string, pinned: boolean) => void | Promise<void>;
  onAddToProject?: (id: string) => void;
  dark: boolean;
  user: AppUser;
  /** KB ライブラリを開く（null = すべての文書）。 */
  onOpenLibrary?: (kbId: string | null) => void;
  /** ライブラリを開いて即ファイル選択を出す（「文書を追加」）。 */

  /** ごみ箱ビューを開く。 */
  onOpenTrash?: () => void;
  /** ライブラリ表示中の KB（undefined = ライブラリ非表示、null = すべての文書）。 */
  activeKbId?: string | null;
  /** ごみ箱ビュー表示中か。 */
  trashActive?: boolean;
  dataSourceCount: number;
}

const drawerBase =
  "max-tablet:fixed max-tablet:inset-y-0 max-tablet:left-0 max-tablet:z-[60] max-tablet:w-[284px] max-tablet:max-w-[86vw] max-tablet:border-r-0 max-tablet:shadow-[8px_0_32px_rgba(0,0,0,0.18)] max-tablet:transition-transform max-tablet:duration-[240ms] max-tablet:ease-[cubic-bezier(0.2,0.8,0.2,1)]";

export function Sidebar(props: SidebarProps) {
  const {
    collapsed, onToggle, threads, activeThreadId, onSelectThread, onNewChat,
    onRenameThread, onDeleteThread, onToggleStar, onAddToProject,
    onOpenLibrary, onOpenTrash, activeKbId, trashActive, dataSourceCount,
  } = props;
  const { t } = useT();
  const [filter, setFilter] = useState("");
  const [menuId, setMenuId] = useState<string | null>(null);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  // アクセス可能 KB。共有 KB があるときだけサイドバーに内訳を列挙する。
  const { kbs } = useKbs();
  const hasSharedKbs = kbs.some((k) => k.kind !== "personal");
  // 共有の KB を作れるのは admin と部門管理者（specs/024 R9）
  const isAdmin = Boolean(props.onOpenAdmin);
  const { departments } = useDepartments(Boolean(onOpenLibrary));
  const managed = isAdmin ? departments : departments.filter((d) => d.my_role === "manager");
  const canCreateKb = Boolean(onOpenLibrary) && (isAdmin || managed.length > 0);
  const [creatingKb, setCreatingKb] = useState(false);
  const search = useThreadSearch(filter);
  const searching = filter.trim() !== "";

  // 本文まで探すのはサーバー（useThreadSearch）。これは結果が来るまでの題名だけの絞り込み。
  const filtered = threads.filter((t) => !searching || t.title.toLowerCase().includes(filter.trim().toLowerCase()));

  if (collapsed) {
    // Icon rail (desktop ≥769px). Hidden entirely on mobile (drawer closes instead).
    return (
      <SidebarRail
        onExpand={onToggle}
        onNew={onNewChat}
        expandLabel={t.sidebar.openSidebar}
        newLabel={t.sidebar.newThread}
      >
        {onOpenLibrary && <SidebarRailButton icon="database" label={t.sidebar.kbHeading} onClick={() => onOpenLibrary(null)} />}
        {onOpenTrash && <SidebarRailButton icon="trash" label={t.sidebar.trash} onClick={onOpenTrash} />}
      </SidebarRail>
    );
  }

  // relativeTime() の実出力に合わせて振り分ける。ja/zh 両言語のパターンを含む。
  // ja: たった今/X分前/X時間前 → today, 昨日/X日前 → this week
  // zh: 刚刚/X分钟前/X小时前 → today, X天前 → this week
  // どれにも当たらないものは「以前」に落としてスレッドが消えないようにする（catch-all）。
  const isToday = (u: string) =>
    u === "今" || u === "たった今" || u === "刚刚" ||
    u.includes("分前") || u.includes("分钟前") ||
    u.includes("時間") || u.includes("小时");
  const isWeek = (u: string) => u === "昨日" || u === "昨天" || u.includes("日前") || u.includes("天前");
  const pinned = filtered.filter((t) => t.pinned);
  const rest = filtered.filter((t) => !t.pinned);
  const groups = [
    { label: t.sidebar.groupPinned, items: pinned },
    { label: t.sidebar.groupToday, items: rest.filter((t) => isToday(t.updated)) },
    { label: t.sidebar.groupThisWeek, items: rest.filter((t) => !isToday(t.updated) && isWeek(t.updated)) },
    { label: t.sidebar.groupEarlier, items: rest.filter((t) => !isToday(t.updated) && !isWeek(t.updated)) },
  ].filter((g) => g.items.length > 0);

  const beginRename = (t: ThreadSummary) => {
    setMenuId(null);
    setRenameId(t.id);
    setRenameValue(t.title);
  };
  const commitRename = async () => {
    const id = renameId;
    const next = renameValue.trim();
    setRenameId(null);
    setRenameValue("");
    if (!id || !next) return;
    const original = threads.find((x) => x.id === id);
    if (!original || next === original.title) return;
    await onRenameThread(id, next);
  };
  const labels = {
    menuLabel: t.sidebar.threadMenuLabel,
    star: t.sidebar.star, unstar: t.sidebar.unstar,
    rename: t.sidebar.rename, delete: t.sidebar.delete,
    addToProject: t.sidebar.addToProject,
  };
  const cancelRename = () => {
    setRenameId(null);
    setRenameValue("");
  };

  return (
    <aside
      className={cn(
        // 半透明 + ぼかし。広い画面では後ろの淡い光が、引き出し（狭い画面）では下の画面が透ける
        "relative flex flex-col overflow-hidden border-r-[0.5px] border-divider bg-bg-2/65 backdrop-blur-xl max-tablet:bg-bg-2/85",
        drawerBase,
        "max-tablet:translate-x-0",
      )}
    >
      {/* Head */}
      <SidebarHeader
        onToggle={onToggle}
        closeLabel={t.sidebar.closeSidebar}
      />

      {/* New thread */}
      <SidebarNewButton label={t.sidebar.newThread} shortcut={SHORTCUT_LABEL.newThread} onClick={onNewChat} />

      {/* Search */}
      <div className="relative mx-3 mb-3">
        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-2">
          <Icon name="search" size={12} />
        </span>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") setFilter(""); }}
          type="search"
          aria-label={t.sidebar.searchPlaceholder}
          placeholder={t.sidebar.searchPlaceholder}
          className="h-[30px] w-full rounded-control border-0 bg-transparent pl-[30px] pr-10 text-footnote text-fg outline-none placeholder:text-muted-2 focus:bg-surface focus:shadow-[0_0_0_1px_var(--divider-strong)]"
        />
        {props.onOpenPalette && !filter && (
          <button
            type="button"
            onClick={props.onOpenPalette}
            aria-label={t.sidebar.openPalette}
            title={t.sidebar.openPalette}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 border-0 bg-transparent p-0 text-mini opacity-70 hover:opacity-100"
          >
            <kbd>{SHORTCUT_LABEL.palette}</kbd>
          </button>
        )}
      </div>

      {/* List */}
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {/* ナレッジベース: チャット履歴より上に置く一級ナビゲーション。
            開いている KB はスレッドと同じアクティブハイライトで示す。 */}
        {/* 検索中は結果を上に出すため、ナレッジベースの欄を隠す */}
        {onOpenLibrary && !searching && (
        <>
        <div className="mb-2" data-tour="kb-section">
          <div className="flex items-center justify-between px-2 pb-1 pt-2">
            <span className="text-mini font-semibold uppercase tracking-[0.06em] text-muted-2">{t.sidebar.kbHeading}</span>
            {canCreateKb && (
              <IconButton size="icon-sm"
                onClick={() => setCreatingKb(true)}
                label={t.sidebar.kbCreate}
                icon="plus"
                iconSize={11}
              />
            )}
          </div>
          {hasSharedKbs ? (
            <>
              <KbRow
                icon="database"
                glyph={{ char: "全", color: "var(--fg)" }}
                label={t.sidebar.kbAllDocuments}
                count={String(dataSourceCount)}
                active={activeKbId === null}
                onClick={() => onOpenLibrary(null)}
              />
              {kbs.map((kb) => (
                <KbRow
                  key={kb.id}
                  icon={kb.kind === "personal" ? "user" : kb.kind === "org" ? "building" : "group"}
                  glyph={kb.kind === "personal" ? undefined : kbGlyph(kb.id, kb.name)}
                  label={kb.kind === "personal" ? t.sidebar.kbPersonal : kb.name}
                  count={String(kb.documentCount)}
                  readOnly={!kb.canWrite}
                  restricted={kb.kind === "org" && !kb.sharedWithEveryone}
                  archived={kb.status === "archived"}
                  active={activeKbId === kb.id}
                  onClick={() => onOpenLibrary(kb.id)}
                />
              ))}
            </>
          ) : (
            // 個人 KB のみなら内訳は冗長なので 1 行に集約。
            <KbRow
              icon="database"
              label={t.sidebar.kbPersonal}
              count={String(dataSourceCount)}
              active={activeKbId !== undefined}
              onClick={() => onOpenLibrary(null)}
            />
          )}

          {/* ごみ箱: 論理削除済み文書の一覧・復元・完全消去。 */}
          {onOpenTrash && <button
            onClick={onOpenTrash}
            className={cn(
              "my-px flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left text-footnote transition-colors",
              trashActive ? "bg-surface text-fg shadow-e1" : "bg-transparent text-muted hover:bg-divider hover:text-fg",
            )}
          >
            <span className={cn("grid w-4 place-items-center", trashActive ? "text-accent" : "text-muted")}>
              <Icon name="trash" size={12} />
            </span>
            <span className="min-w-0 flex-1 truncate">{t.sidebar.trash}</span>
          </button>}
        </div>

        <div className="mx-2 my-3 h-px bg-divider" />
        </>
        )}

        {searching && (
          <SidebarSearchResults
            query={filter}
            state={search}
            localMatches={filtered}
            activeThreadId={activeThreadId}
            onSelect={onSelectThread}
          />
        )}

        {!searching && groups.map((g) => (
          <div key={g.label} className="mb-2">
            <div className="px-2 pb-1 pt-2 text-mini font-semibold uppercase tracking-[0.06em] text-muted-2">
              {g.label}
            </div>
            {/* map の要素名はここだけ th とする（外側 useT() の t.sidebar.* を同スコープで
                参照するため、ThreadSummary の慣例名 t と衝突させない）。 */}
            {g.items.map((th) => (
              <ThreadRow
                key={th.id}
                thread={th}
                active={th.id === activeThreadId}
                renaming={renameId === th.id}
                renameValue={renameValue}
                menuOpen={menuId === th.id}
                labels={labels}
                onRenameChange={setRenameValue}
                onRenameCommit={commitRename}
                onRenameCancel={cancelRename}
                onSelect={() => onSelectThread(th.id)}
                onMenuOpenChange={(o) => setMenuId(o ? th.id : null)}
                menu={
                  menuId === th.id && (
                    <ThreadMenuItems
                      thread={th}
                      labels={labels}
                      onStar={() => onToggleStar(th.id, !th.pinned)}
                      onRename={() => beginRename(th)}
                      onAddProject={onAddToProject ? () => onAddToProject(th.id) : undefined}
                      onDelete={() => onDeleteThread(th.id)}
                    />
                  )
                }
                trailing={
                  th.running ? (
                    <span
                      aria-label={t.sidebar.threadRunning}
                      className="block h-2.5 w-2.5 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent"
                    />
                  ) : undefined
                }
              />
            ))}
          </div>
        ))}
      </div>

      <SidebarUserFooter
        user={props.user}
        dark={props.dark}
        onToggleTheme={props.onToggleTheme}
        onSignOut={props.onSignOut}
        onOpenSettings={props.onOpenSettings}
        onOpenAdmin={props.onOpenAdmin}
        onOpenWorkCalendar={props.onOpenWorkCalendar}
        onOpenHelp={props.onOpenHelp}
      />

      {creatingKb && (
        <CreateKbDialog
          isAdmin={isAdmin}
          departments={managed}
          onClose={() => setCreatingKb(false)}
          onCreated={(id) => {
            setCreatingKb(false);
            void refreshKbs().then(() => onOpenLibrary?.(id));
          }}
        />
      )}

    </aside>
  );
}

function KbRow({ icon, glyph, label, count, readOnly, restricted, archived, active, onClick }: {
  icon: IconName;
  /** 色付きの字標（共有 KB を見分ける。specs/025 R44）。無ければ icon を出す */
  glyph?: { char: string; color: string };
  label: string; count?: string; readOnly?: boolean; restricted?: boolean; archived?: boolean; active?: boolean; onClick: () => void;
}) {
  const { t } = useT();
  return (
    <button
      onClick={onClick}
      className={cn(
        "my-px flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left text-footnote transition-colors",
        // 選択強調は背景のみ（ThreadRow と同じ規約。font-weight は CJK 合成太字を避けるため使わない）。
        active ? "bg-surface text-fg shadow-e1" : "bg-transparent text-fg-2 hover:bg-divider",
      )}
    >
      {glyph ? (
        <span
          aria-hidden
          className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded-[5px] text-mini font-bold leading-none text-bg"
          style={{ backgroundColor: glyph.color }}
        >
          {glyph.char}
        </span>
      ) : (
        <span className={cn("grid w-[18px] place-items-center", active ? "text-accent" : "text-muted")}>
          <Icon name={icon} size={13} />
        </span>
      )}
      <span className="min-w-0 flex-1 truncate" title={label}>{label}</span>
      {/* 鍵 = 限られた人だけが使える（全員には共有していない）。閲覧のみは文字だけ（specs/024 R14） */}
      {restricted && (
        <span className="shrink-0 text-muted-2" title={t.sidebar.kbRestricted} aria-label={t.sidebar.kbRestricted}>
          <Icon name="lock" size={10} />
        </span>
      )}
      {readOnly && (
        <Badge>{t.sidebar.kbReadOnlyBadge}</Badge>
      )}
      {/* 归档(archived)状態は検索範囲ドロップダウンと表示を揃える（同じ KB が画面ごとに違って見えるのを防ぐ）。 */}
      {archived && (
        <Badge tone="outline">{t.sidebar.kbArchivedBadge}</Badge>
      )}
      {count != null && <span className="shrink-0 font-mono text-mini text-muted">{count}</span>}
    </button>
  );
}
