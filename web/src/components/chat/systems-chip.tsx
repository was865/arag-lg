"use client";
/**
 * 入力欄の「社内システム」の札（specs/033 R19）。この利用者が使える社内システムと、接続の状態を小さな印で出す。
 * 状態は runner と api の本当の死活の確認（30 秒）と、回答中の呼び出しで分かった死活から。回答が終わったらすぐ読み直す。
 * 作った動きは出さない。使えるシステムが無ければ何も出さない。
 */
import { useEffect, useState } from "react";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { chatApi, type SystemStatus } from "@/lib/chat/api";
import { formatLocalMinute } from "@/lib/datetime";
import { cn } from "@/lib/utils";

const POLL_MS = 30_000;

function Dot({ state }: { state: SystemStatus["state"] }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        state === "ok" && "bg-fg-2",
        state === "slow" && "border border-fg-2 bg-transparent",
        state === "down" && "bg-danger",
      )}
    />
  );
}

export function SystemsChip({ className, running = false }: { className?: string; running?: boolean }) {
  const { t } = useT();
  const [systems, setSystems] = useState<SystemStatus[] | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      chatApi
        .systemsStatus()
        .then((xs) => alive && setSystems(xs))
        .catch(() => alive && setSystems(null));
    void load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // 回答が終わったとき（running が false に戻ったとき）も読み直す。呼び出しで止まっていると分かった状態をすぐ出す
  }, [running]);
  if (!systems || systems.length === 0) return null;
  const detail = systems
    .map((s) =>
      interpolate(t.chat.systemsStateDetail, {
        label: s.label,
        state: t.chat.systemsState[s.state] ?? s.state,
        ms: String(s.ms),
        at: formatLocalMinute(s.checked_at),
      }),
    )
    .join("\n");
  const down = systems.filter((s) => s.state === "down");
  return (
    <span
      className={cn("inline-flex h-7 shrink-0 items-center gap-1.5 rounded-control px-2 text-footnote text-muted", className)}
      title={detail}
      aria-label={detail}
      data-testid="systems-chip"
    >
      <span className="max-md:hidden">{t.chat.systemsLabel}</span>
      <span className="inline-flex items-center gap-[3px]">
        {systems.map((s) => (
          <Dot key={s.name} state={s.state} />
        ))}
      </span>
      {down.length > 0 && (
        <span className="text-danger">
          {down.map((s) => s.label).join("・")} {t.chat.systemsState.down}
        </span>
      )}
    </span>
  );
}
