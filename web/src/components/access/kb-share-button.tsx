"use client";

/** ライブラリの見出しに出す共有の要約と「共有」ボタン（specs/024 R11）。 */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/icons";
import { KbShareDialog } from "@/components/access/kb-share-dialog";
import { refreshKbs } from "@/hooks/use-kbs";
import { accessApi } from "@/lib/access/api";
import { effectiveRoles, shareSummary, type Share } from "@/lib/access/shares";

export function KbShareButton({ kbId, kbName }: { kbId: string; kbName: string }) {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<{ key: string; text: string } | null>(null);
  const [version, setVersion] = useState(0);
  const key = `${kbId}:${version}`;

  useEffect(() => {
    let alive = true;
    Promise.all([accessApi.shares(kbId), accessApi.departments()]).then(
      ([s, depts]) => {
        if (!alive) return;
        const shares = s.shares as Share[];
        const roles = effectiveRoles(shares, s.department_members, []);
        const editors = [...roles.values()].filter((r) => r !== "viewer").length;
        const name = (id: string) => depts.find((d) => d.id === id)?.name ?? "部門";
        setSummary({ key, text: shareSummary(shares, name, editors) });
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [kbId, key]);

  const text = summary?.key === key ? summary.text : null;
  return (
    <>
      <Button variant="secondary" size="sm"
        onClick={() => setOpen(true)}
        title={text ?? "共有"}
        className="min-w-0"
      >
        <Icon name="group" size={13} />
        <span className="max-md:hidden">共有</span>
        {text && <span className="min-w-0 max-w-[260px] truncate font-normal text-muted max-xl:hidden">{text}</span>}
      </Button>
      {open && (
        <KbShareDialog
          kbId={kbId}
          kbName={kbName}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setVersion((v) => v + 1);
            void refreshKbs();
          }}
        />
      )}
    </>
  );
}
