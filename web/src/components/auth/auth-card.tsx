/** 認証画面の共通部品（カード・入力欄・ボタン）。 */
import type { ReactNode } from "react";
import { BrandMark } from "@/components/icons";
import { cn } from "@/lib/utils";

export const FIELD =
  "h-10 w-full rounded-[10px] border-[0.5px] border-divider-strong bg-surface px-3 text-[14px] text-fg outline-none placeholder:text-muted-2 focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]";

export const PRIMARY =
  "inline-flex h-10 w-full items-center justify-center gap-2 rounded-[10px] border-0 bg-accent text-[14px] font-semibold text-white hover:brightness-105 disabled:cursor-default disabled:opacity-60";

export function AuthCard({ title, description, children, footer }: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="relative grid min-h-dvh w-full place-items-center overflow-hidden bg-bg px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,var(--accent-soft),transparent_70%)]"
      />
      <div className="relative flex w-[400px] max-w-full flex-col rounded-[18px] border-[0.5px] border-divider-strong bg-surface px-9 pb-7 pt-9 shadow-e3 max-md:px-6">
        <div className="mb-6 flex items-center gap-2 text-[14px] font-semibold text-fg">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-white">
            <BrandMark size={15} />
          </span>
          ARag
        </div>
        <h1 className="m-0 mb-1.5 text-[22px] font-bold tracking-[-0.01em] text-fg">{title}</h1>
        {description && <p className="m-0 mb-6 text-[13.5px] leading-[1.6] text-muted">{description}</p>}
        {children}
        {footer && <div className="mt-6 text-center text-[13px] text-muted">{footer}</div>}
      </div>
    </main>
  );
}

export function Field({ label, children, aside }: { label: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center justify-between text-[12px] font-semibold text-fg-2">
        {label}
        {aside}
      </span>
      {children}
    </label>
  );
}

export function Notice({ tone, children }: { tone: "error" | "info"; children: ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "rounded-[10px] px-3 py-2.5 text-[12.5px] leading-[1.55]",
        tone === "error" ? "bg-danger-soft text-danger" : "border-[0.5px] border-divider-strong bg-surface-2 text-fg-2",
      )}
    >
      {children}
    </div>
  );
}

export function Spinner() {
  return <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />;
}

export function LinkButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="border-0 bg-transparent p-0 text-[12.5px] font-medium text-accent hover:underline">
      {children}
    </button>
  );
}
