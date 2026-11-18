"use client";

/** チャットの上部バー（スレッドの題・状態・出典・共有・外観）。 */
import { Icon } from "@/components/icons";
import { ThemeToggle } from "@/components/sidebar/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button, IconButton } from "@/components/ui/button";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { cn } from "@/lib/utils";

export type ChatPhase = "empty" | "running" | "cancelled" | "done";

export function ChatHeader({
  phase,
  home,
  scrolled,
  title,
  emptyTitle,
  reconnecting,
  sourceCount,
  shared,
  canShare,
  dark,
  onOpenMenu,
  onOpenSources,
  onShare,
  onToggleTheme,
}: {
  phase: ChatPhase;
  /** 首ページ（地を透かす） */
  home: boolean;
  /** 会話を下へ送ったか（区切り線を出す） */
  scrolled: boolean;
  title: string;
  /** まだ質問の無いスレッドの題（新規なら null） */
  emptyTitle: string | null;
  reconnecting: boolean;
  /** 出典の数。0 か右パネルを開いているときはボタンを出さない */
  sourceCount: number;
  shared: boolean;
  canShare: boolean;
  dark: boolean;
  onOpenMenu: () => void;
  onOpenSources: () => void;
  onShare: () => void;
  onToggleTheme: () => void;
}) {
  const { t } = useT();
  return (
    <header
      className={cn(
        "sticky top-0 z-[5] flex h-[52px] items-center gap-2 border-b-[0.5px] px-[18px] max-md:gap-1 max-md:px-2.5",
        // 区切り線は中身が下へ流れたときだけ淡く出す（上端にいる間は線を引かない）
        "transition-[border-color] duration-(--duration-mid)",
        home ? "border-transparent bg-transparent" : scrolled ? "border-divider bg-bg" : "border-transparent bg-bg",
      )}
    >
      <IconButton
        label={t.workspace.openMenuAriaLabel}
        tooltip={false}
        icon="menu"
        iconSize={15}
        className="-ml-1 hidden h-[34px] w-[34px] text-fg max-md:inline-flex"
        onClick={onOpenMenu}
      />
      <div className="flex min-w-0 flex-1 items-center gap-2 text-body font-semibold text-fg max-md:gap-1.5">
        {phase === "empty" ? (
          <span className="font-medium text-muted">{emptyTitle ?? t.workspace.headerNewThread}</span>
        ) : (
          <>
            <span className="min-w-0 flex-1 truncate">{title.slice(0, 80) || t.workspace.headerThreadFallback}</span>
            {phase === "cancelled" && (
              <Badge tone="danger" mono className="ml-1.5 py-0.5">
                {t.workspace.badgeCancelled}
              </Badge>
            )}
            {phase === "running" && (
              <Badge
                tone="accent"
                mono
                className="ml-1.5 py-0.5 before:h-[5px] before:w-[5px] before:rounded-full before:bg-accent before:[animation:ar-pulse_1.2s_ease-in-out_infinite]"
              >
                {reconnecting ? t.chat.reconnecting : t.workspace.badgeRunning}
              </Badge>
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-1.5 max-md:gap-0.5">
        {phase !== "empty" && sourceCount > 0 && (
          <button
            className="inline-flex h-[30px] items-center gap-1.5 rounded-control border border-accent bg-transparent px-2.5 text-footnote font-medium text-accent hover:bg-accent-soft max-md:h-8 max-md:px-2.5 max-md:text-caption"
            onClick={onOpenSources}
          >
            <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
              <path d="M3 3h10v10H3z" stroke="currentColor" strokeWidth="1.4" fill="none" />
              <path d="M10 3v10" stroke="currentColor" strokeWidth="1.4" />
            </svg>
            {interpolate(t.workspace.btnSources, { n: String(sourceCount) })}
          </button>
        )}
        {canShare && phase !== "empty" && (
          <Button
            variant="ghost"
            size="sm"
            className="text-fg-2 hover:text-fg max-md:w-8 max-md:px-0"
            onClick={onShare}
            aria-label="共有"
            title="共有"
          >
            <Icon name={shared ? "link" : "share"} size={13} />
            <span className="max-md:hidden">共有</span>
          </Button>
        )}
        <ThemeToggle dark={dark} onToggle={onToggleTheme} />
      </div>
    </header>
  );
}
