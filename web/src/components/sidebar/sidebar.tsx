"use client";

import { SHORTCUT_LABEL } from "@/lib/shortcuts";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { SidebarHeader } from "@/components/sidebar/sidebar-header";
import { SidebarNewButton } from "@/components/sidebar/sidebar-new-button";
import { SidebarRail, SidebarRailButton } from "@/components/sidebar/sidebar-rail";
import { SidebarUserFooter } from "@/components/sidebar/sidebar-footer";
import { ThreadRow, ThreadMenu } from "@/components/sidebar/thread-item";
import { cn } from "@/lib/utils";
import type { AppUser, ThreadSummary } from "@/lib/types";
import { useKbs } from "@/hooks/use-kbs";
import { useT } from "@/i18n/context";

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

interface MenuAnchor {
  id: string;
  rect: { left: number; top: number; bottom: number; right: number };
}

export function Sidebar(props: SidebarProps) {
  const {
    collapsed, onToggle, threads, activeThreadId, onSelectThread, onNewChat,
    onRenameThread, onDeleteThread, onToggleStar, onAddToProject,
    onOpenLibrary, onOpenTrash, activeKbId, trashActive, dataSourceCount,
  } = props;
  const { t } = useT();
  const [filter, setFilter] = useState("");
  const [menuAnchor, setMenuAnchor] = useState<MenuAnchor | null>(null);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  // アクセス可能 KB。共有 KB があるときだけサイドバーに内訳を列挙する。
  const { kbs } = useKbs();
  const hasSharedKbs = kbs.some((k) => k.kind !== "personal");

  const filtered = threads.filter((t) => !filter || t.title.toLowerCase().includes(filter.toLowerCase()));

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
    setMenuAnchor(null);
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
  const cancelRename = () => {
    setRenameId(null);
    setRenameValue("");
  };

  const menuThread = menuAnchor ? threads.find((t) => t.id === menuAnchor.id) ?? null : null;

  return (
    <aside
      className={cn(
        "relative flex flex-col overflow-hidden border-r-[0.5px] border-divider bg-bg-2",
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
          placeholder={t.sidebar.searchPlaceholder}
          className="h-[30px] w-full rounded-lg border-0 bg-transparent pl-[30px] pr-2.5 text-[12.5px] text-fg outline-none placeholder:text-muted-2 focus:bg-surface focus:shadow-[0_0_0_1px_var(--divider-strong)]"
        />
      </div>

      {/* List */}
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {/* ナレッジベース: チャット履歴より上に置く一級ナビゲーション。
            開いている KB はスレッドと同じアクティブハイライトで示す。 */}
        {onOpenLibrary && (
        <>
        <div className="mb-2" data-tour="kb-section">
          <div className="px-2 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-2">
            {t.sidebar.kbHeading}
          </div>
          {hasSharedKbs ? (
            <>
              <KbRow
                icon="database"
                label={t.sidebar.kbAllDocuments}
                count={String(dataSourceCount)}
                active={activeKbId === null}
                onClick={() => onOpenLibrary(null)}
              />
              {kbs.map((kb) => (
                <KbRow
                  key={kb.id}
                  icon={kb.kind === "personal" ? "user" : kb.kind === "org" ? "building" : "group"}
                  label={kb.kind === "personal" ? t.sidebar.kbPersonal : kb.name}
                  count={String(kb.documentCount)}
                  readOnly={!kb.canWrite}
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
              "my-px flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] transition-colors",
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

        {groups.map((g) => (
          <div key={g.label} className="mb-2">
            <div className="px-2 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-2">
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
                menuOpen={menuAnchor?.id === th.id}
                labels={{
                  menuLabel: t.sidebar.threadMenuLabel,
                  star: t.sidebar.star, unstar: t.sidebar.unstar,
                  rename: t.sidebar.rename, delete: t.sidebar.delete,
                  addToProject: t.sidebar.addToProject,
                }}
                onRenameChange={setRenameValue}
                onRenameCommit={commitRename}
                onRenameCancel={cancelRename}
                onSelect={() => onSelectThread(th.id)}
                onOpenMenu={(rect) => setMenuAnchor({ id: th.id, rect })}
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

      {menuAnchor && menuThread && (
        <ThreadMenu
          thread={menuThread}
          anchor={menuAnchor.rect}
          labels={{
            menuLabel: t.sidebar.threadMenuLabel,
            star: t.sidebar.star, unstar: t.sidebar.unstar,
            rename: t.sidebar.rename, delete: t.sidebar.delete,
            addToProject: t.sidebar.addToProject,
          }}
          onClose={() => setMenuAnchor(null)}
          onStar={() => {
            const target = menuThread;
            setMenuAnchor(null);
            onToggleStar(target.id, !target.pinned);
          }}
          onRename={() => beginRename(menuThread)}
          onAddProject={onAddToProject ? () => {
            const target = menuThread;
            setMenuAnchor(null);
            onAddToProject(target.id);
          } : undefined}
          onDelete={() => {
            const target = menuThread;
            setMenuAnchor(null);
            onDeleteThread(target.id);
          }}
        />
      )}
    </aside>
  );
}

function KbRow({ icon, label, count, readOnly, archived, active, onClick }: {
  icon: IconName; label: string; count?: string; readOnly?: boolean; archived?: boolean; active?: boolean; onClick: () => void;
}) {
  const { t } = useT();
  return (
    <button
      onClick={onClick}
      className={cn(
        "my-px flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] transition-colors",
        // 選択強調は背景のみ（ThreadRow と同じ規約。font-weight は CJK 合成太字を避けるため使わない）。
        active ? "bg-surface text-fg shadow-e1" : "bg-transparent text-fg-2 hover:bg-divider",
      )}
    >
      <span className={cn("grid w-4 place-items-center", active ? "text-accent" : "text-muted")}>
        <Icon name={icon} size={13} />
      </span>
      <span className="min-w-0 flex-1 truncate" title={label}>{label}</span>
      {readOnly && (
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-divider px-1.5 py-px text-[9.5px] font-semibold text-muted">
          <Icon name="lock" size={9} />
          {t.sidebar.kbReadOnlyBadge}
        </span>
      )}
      {/* 归档(archived)状態は検索範囲ドロップダウンと表示を揃える（同じ KB が画面ごとに違って見えるのを防ぐ）。 */}
      {archived && (
        <span className="shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-[9.5px] font-semibold text-muted-2">
          {t.sidebar.kbArchivedBadge}
        </span>
      )}
      {count != null && <span className="shrink-0 font-mono text-[10.5px] text-muted">{count}</span>}
    </button>
  );
}
