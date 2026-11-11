"use client";

/**
 * 共有のナレッジベースの管理（specs/024 R10）。
 * admin は中身を読めなくても共有リストは管理できる（Q1 案 A）。自分を足す操作は監査ログに残る。
 */
import { ListSkeleton } from "@/components/ui/skeleton";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { AdminHeader } from "@/components/admin/admin-header";
import { CreateKbDialog } from "@/components/access/create-kb-dialog";
import { KbShareDialog } from "@/components/access/kb-share-dialog";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { refreshKbs } from "@/hooks/use-kbs";
import { useDepartments } from "@/hooks/use-departments";
import { accessApi, type KbOut } from "@/lib/access/api";
import { ROLE_LABEL } from "@/lib/access/shares";
import { ApiError } from "@/lib/chat/api";
import { formatDate } from "@/lib/library/view";
import { cn } from "@/lib/utils";
import { SearchField } from "@/components/ui/input";

export function KbsView() {
  const push = useToast();
  const { departments } = useDepartments();
  const [kbs, setKbs] = useState<KbOut[] | null>(null);
  const [query, setQuery] = useState("");
  const [sharing, setSharing] = useState<KbOut | null>(null);
  const [creating, setCreating] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    accessApi.manageableKbs().then(
      (ks) => alive && setKbs(ks.filter((k) => k.kind === "org")),
      (e: unknown) => {
        if (!alive) return;
        push(e instanceof ApiError ? e.message : "一覧を取得できませんでした", "error");
        setKbs((k) => k ?? []);
      },
    );
    return () => {
      alive = false;
    };
  }, [tick, push]);

  const q = query.trim().toLowerCase();
  const shown = (kbs ?? []).filter((k) => !q || k.name.toLowerCase().includes(q));

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] bg-bg">
      <AdminHeader current="kbs">
        {kbs && <span className="font-mono text-caption text-muted max-md:hidden">{kbs.length} 件</span>}
        <Button variant="primary" size="sm"
          onClick={() => setCreating(true)}
        >
          <Icon name="plus" size={13} />
          作成
        </Button>
      </AdminHeader>

      <div className="border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <SearchField
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onClear={() => setQuery("")}
          placeholder="名前で探す"
          className="mx-auto max-w-[1000px]"
        />
      </div>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto my-4 w-[calc(100%-36px)] max-w-[1000px] rounded-card border-[0.5px] border-divider-strong bg-surface px-3 pb-3 pt-1 shadow-e1 max-md:my-2 max-md:w-[calc(100%-16px)] max-md:px-1.5">
          <div className="grid grid-cols-[minmax(0,1fr)_150px_70px_70px_72px] gap-3 border-b-[0.5px] border-divider px-2 py-2 text-mini font-semibold uppercase tracking-[0.05em] text-muted-2 max-md:hidden">
            <span>名前</span>
            <span>あなたの役割</span>
            <span className="text-right">文書</span>
            <span className="text-right">作成日</span>
            <span />
          </div>
          {kbs === null ? (
            <ListSkeleton />
          ) : shown.length === 0 ? (
            <p className="py-16 text-center text-body text-muted">
              {kbs.length === 0 ? "共有のナレッジベースはまだありません" : "条件に合うナレッジベースはありません"}
            </p>
          ) : (
            shown.map((k) => (
              <div
                key={k.id}
                className={cn(
                  "grid grid-cols-[minmax(0,1fr)_150px_70px_70px_72px] items-center gap-3 rounded-control px-2 py-2 hover:bg-surface-2",
                  "max-md:grid-cols-[minmax(0,1fr)_auto]",
                )}
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-surface-2 text-muted">
                    <Icon name={k.shared_with_everyone ? "building" : "lock"} size={14} />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-body font-medium text-fg">
                      {k.name}
                      {k.status === "archived" && <span className="ml-1.5 text-caption font-normal text-muted">アーカイブ</span>}
                    </div>
                    <div className="truncate text-caption text-muted">
                      {k.shared_with_everyone ? "社内の全員が閲覧" : "限られた部門・人だけ"}
                      <span className="hidden max-md:inline"> · {k.role ? ROLE_LABEL[k.role] : "共有リスト外"}</span>
                    </div>
                  </div>
                </div>
                <span className={cn("text-footnote max-md:hidden", k.role ? "text-fg-2" : "text-muted")}>
                  {k.role ? ROLE_LABEL[k.role] : "—（内容は閲覧不可）"}
                </span>
                <span className="text-right font-mono text-caption text-muted max-md:hidden">{k.role ? k.document_count : "—"}</span>
                <span className="text-right font-mono text-caption text-muted max-md:hidden">{formatDate(k.created_at)}</span>
                <Button variant="secondary" size="sm"
                  onClick={() => setSharing(k)}
                  className="justify-self-end"
                >
                  <Icon name="group" size={12} />
                  共有
                </Button>
              </div>
            ))
          )}
          <p className="m-0 mt-4 px-2 text-caption leading-[1.6] text-muted">
            管理者はすべての共有ナレッジベースの「共有」を変えられますが、共有リストに入っていないナレッジベースの中身は見られません。自分を共有リストに加えると、監査ログに残ります。
          </p>
        </div>
      </div>
      {sharing && (
        <KbShareDialog
          kbId={sharing.id}
          kbName={sharing.name}
          onClose={() => setSharing(null)}
          onSaved={() => {
            reload();
            void refreshKbs();
          }}
        />
      )}
      {creating && (
        <CreateKbDialog
          isAdmin
          departments={departments}
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            reload();
            void refreshKbs();
          }}
        />
      )}
    </div>
  );
}
