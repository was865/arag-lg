"use client";

/** メンバー管理（specs/010-admin-members）。一覧・招待・役割の変更・停止と再開。 */
import { useCallback, useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { MemberAccessDialog } from "@/components/admin/member-access-dialog";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { useConfirm } from "@/hooks/use-confirm";
import {
  ASSIGNABLE_ROLES,
  memberActionError,
  memberStatus,
  ROLE_LABEL,
  STATUS_LABEL,
  type MemberAction,
  type Role,
} from "@/lib/admin/members";
import { initialsOf } from "@/lib/auth/user";
import { formatDate } from "@/lib/library/view";
import { cn } from "@/lib/utils";

interface Member {
  id: string;
  name: string;
  email: string;
  role: string;
  emailVerified: boolean;
  banned: boolean;
  createdAt: string;
}

interface ListOut {
  items: Member[];
  me: string;
  myRole: string;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...init, headers: { "content-type": "application/json", ...init?.headers } });
  const body = (await res.json().catch(() => null)) as (T & { error?: { message?: string } }) | null;
  if (!res.ok) throw new Error(body?.error?.message ?? "通信に失敗しました");
  return body as T;
}

const STATUS_TONE = { active: "text-muted", unverified: "text-accent", banned: "text-danger" } as const;

export function MembersView() {
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const [data, setData] = useState<ListOut | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [inviting, setInviting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Member | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setSearch(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const reload = useCallback(async () => {
    try {
      setData(await call<ListOut>(`/api/admin/members${search ? `?q=${encodeURIComponent(search)}` : ""}`));
    } catch (e) {
      push(e instanceof Error ? e.message : "一覧を取得できませんでした", "error");
      setData((d) => d ?? { items: [], me: "", myRole: "" });
    }
  }, [search, push]);

  useEffect(() => {
    let alive = true;
    call<ListOut>(`/api/admin/members${search ? `?q=${encodeURIComponent(search)}` : ""}`).then(
      (d) => alive && setData(d),
      (e: unknown) => {
        if (!alive) return;
        push(e instanceof Error ? e.message : "一覧を取得できませんでした", "error");
        setData((d) => d ?? { items: [], me: "", myRole: "" });
      },
    );
    return () => {
      alive = false;
    };
  }, [search, push]);

  const actor = data ? { id: data.me, role: data.myRole } : null;
  const allowed = (m: Member, a: MemberAction) => Boolean(actor) && memberActionError(actor!, m, a) === null;

  const patch = async (m: Member, body: object, done: string) => {
    setBusy(m.id);
    try {
      await call(`/api/admin/members/${encodeURIComponent(m.id)}`, { method: "PATCH", body: JSON.stringify(body) });
      push(done, "success");
      await reload();
    } catch (e) {
      push(e instanceof Error ? e.message : "変更できませんでした", "error");
    } finally {
      setBusy(null);
    }
  };

  const ban = async (m: Member) => {
    const ok = await confirm({
      title: `${m.name || m.email} さんを停止しますか？`,
      description: "ログインできなくなり、ログイン中の画面も数分のうちに使えなくなります。あとで再開できます。",
      confirmLabel: "停止する",
      tone: "danger",
    });
    if (ok) await patch(m, { banned: true }, `${m.name || m.email} さんを停止しました`);
  };

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] bg-bg">
      <AdminHeader current="members">
        {data && <span className="font-mono text-[11px] text-muted max-md:hidden">{data.items.length} 人</span>}
        <button
          onClick={() => setInviting(true)}
          className="inline-flex h-[30px] items-center gap-1.5 rounded-lg bg-accent px-3 text-[12px] font-semibold text-white hover:brightness-105"
        >
          <Icon name="plus" size={13} />
          招待
        </button>
      </AdminHeader>

      <div className="border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <label className="mx-auto flex h-8 max-w-[1000px] items-center gap-2 rounded-lg border-[0.5px] border-divider-strong bg-surface px-2.5 text-muted focus-within:border-accent">
          <Icon name="search" size={13} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="名前・メールで探す"
            className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-fg outline-none placeholder:text-muted-2"
          />
        </label>
      </div>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-[1000px] px-[18px] pb-10 pt-2 max-md:px-2">
          <div className="grid grid-cols-[minmax(0,1fr)_130px_80px_70px_32px] gap-3 border-b-[0.5px] border-divider px-2 py-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-2 max-md:hidden">
            <span>名前</span>
            <span>役割</span>
            <span>状態</span>
            <span className="text-right">登録日</span>
            <span />
          </div>
          {data === null ? (
            <div className="grid h-40 place-items-center">
              <span className="h-6 w-6 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
            </div>
          ) : data.items.length === 0 ? (
            <p className="py-16 text-center text-[13px] text-muted">条件に合うメンバーはいません</p>
          ) : (
            data.items.map((m) => {
              const st = memberStatus(m);
              const me = m.id === data.me;
              const canRole = ASSIGNABLE_ROLES.some((r) => r !== m.role && allowed(m, { kind: "role", role: r }));
              const canBan = allowed(m, { kind: m.banned ? "unban" : "ban" });
              return (
                <div
                  key={m.id}
                  className={cn(
                    "grid grid-cols-[minmax(0,1fr)_130px_80px_70px_32px] items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-2",
                    "max-md:grid-cols-[minmax(0,1fr)_auto_32px] max-md:gap-2",
                    busy === m.id && "opacity-60",
                  )}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-[11.5px] font-bold text-accent">
                      {initialsOf(m.name, m.email)}
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium text-fg">
                        {m.name || "（名前なし）"}
                        {me && <span className="ml-1.5 text-[11px] font-normal text-muted">（あなた）</span>}
                      </div>
                      <div className="truncate text-[11.5px] text-muted">
                        {m.email}
                        <span className={cn("hidden max-md:inline", STATUS_TONE[st])}> · {STATUS_LABEL[st]}</span>
                      </div>
                    </div>
                  </div>
                  <div>
                    {canRole ? (
                      <select
                        value={m.role}
                        disabled={busy === m.id}
                        aria-label={`${m.name || m.email} さんの役割`}
                        onChange={(e) =>
                          void patch(m, { role: e.target.value }, `役割を「${ROLE_LABEL[e.target.value as Role]}」にしました`)
                        }
                        className="h-7 rounded-md border-[0.5px] border-divider-strong bg-surface px-1.5 text-[12px] text-fg"
                      >
                        {ASSIGNABLE_ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABEL[r]}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-[12px] text-fg-2">{ROLE_LABEL[m.role as Role] ?? m.role}</span>
                    )}
                  </div>
                  <span className={cn("text-[12px] max-md:hidden", STATUS_TONE[st])}>{STATUS_LABEL[st]}</span>
                  <span className="text-right font-mono text-[11px] text-muted max-md:hidden">{formatDate(m.createdAt)}</span>
                  <MemberMenu
                    disabled={busy === m.id}
                    canBan={canBan}
                    banned={m.banned}
                    canResend={canBan && !m.banned}
                    onBan={() => void ban(m)}
                    onUnban={() => void patch(m, { banned: false }, `${m.name || m.email} さんを再開しました`)}
                    onResend={() => void patch(m, { resendInvite: true }, "パスワード設定のリンクを送りました")}
                    onAccess={() => setViewing(m)}
                  />
                </div>
              );
            })
          )}
          <p className="m-0 mt-4 px-2 text-[11.5px] leading-[1.6] text-muted">
            管理者はメンバーの招待・停止ができます。管理者の追加・変更は owner だけが行えます。
          </p>
        </div>
      </div>
      {inviting && actor && (
        <InviteDialog
          canInviteAdmin={actor.role === "owner"}
          onClose={() => setInviting(false)}
          onDone={() => {
            setInviting(false);
            void reload();
          }}
        />
      )}
      {viewing && (
        <MemberAccessDialog
          userId={viewing.id}
          name={viewing.name || viewing.email}
          onClose={() => setViewing(null)}
        />
      )}
      {dialog}
    </div>
  );
}

function MemberMenu({
  disabled,
  canBan,
  banned,
  canResend,
  onBan,
  onUnban,
  onResend,
  onAccess,
}: {
  disabled: boolean;
  canBan: boolean;
  banned: boolean;
  canResend: boolean;
  onBan: () => void;
  onUnban: () => void;
  onResend: () => void;
  onAccess: () => void;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);
  const item = "flex w-full items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-[12.5px] hover:bg-divider";
  return (
    <span className="relative justify-self-end">
      <button
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((x) => !x);
        }}
        aria-label="操作"
        aria-expanded={open}
        className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg disabled:invisible"
      >
        <Icon name="more" size={14} />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-8 z-20 w-max min-w-[160px] animate-pop-in rounded-[10px] border-[0.5px] border-divider-strong bg-surface p-1 shadow-e2"
        >
          <button role="menuitem" className={cn(item, "text-fg")} onClick={onAccess}>
            <Icon name="database" size={13} />
            閲覧できるナレッジベース
          </button>
          {canResend && (
            <button role="menuitem" className={cn(item, "text-fg")} onClick={onResend}>
              <Icon name="mail" size={13} />
              パスワード設定のリンクを送る
            </button>
          )}
          {!canBan ? null : banned ? (
            <button role="menuitem" className={cn(item, "text-fg")} onClick={onUnban}>
              <Icon name="refresh" size={13} />
              再開する
            </button>
          ) : (
            <button role="menuitem" className={cn(item, "text-danger")} onClick={onBan}>
              <Icon name="lock" size={13} />
              停止する
            </button>
          )}
        </div>
      )}
    </span>
  );
}

function InviteDialog({
  canInviteAdmin,
  onClose,
  onDone,
}: {
  canInviteAdmin: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const push = useToast();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSending(true);
    try {
      await call("/api/admin/members", { method: "POST", body: JSON.stringify({ email, name, role }) });
      push(`${email} に招待メールを送りました`, "success");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "招待できませんでした");
    } finally {
      setSending(false);
    }
  };

  const field =
    "h-9 w-full rounded-[9px] border-[0.5px] border-divider-strong bg-surface px-3 text-[13.5px] text-fg outline-none focus:border-accent";
  return (
    <div
      className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label="メンバーを招待"
        onSubmit={(e) => void submit(e)}
        onClick={(e) => e.stopPropagation()}
        className="flex w-[420px] max-w-full animate-pop-in flex-col gap-3 rounded-[16px] border-[0.5px] border-divider-strong bg-surface p-5 shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0] max-md:pb-[max(20px,env(safe-area-inset-bottom))]"
      >
        <h3 className="m-0 text-[15px] font-bold text-fg">メンバーを招待</h3>
        <p className="m-0 text-[12px] leading-[1.6] text-muted">
          パスワードを設定するリンクをメールで送ります（1 時間有効）。
        </p>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-fg-2">
          メールアドレス
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-fg-2">
          名前
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={field} />
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-medium text-fg-2">
          役割
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as "member" | "admin")}
            className={field}
          >
            <option value="member">メンバー</option>
            {canInviteAdmin && <option value="admin">管理者</option>}
          </select>
        </label>
        {error && <p className="m-0 text-[12px] text-danger">{error}</p>}
        <div className="mt-1 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded-[9px] px-3.5 text-[13px] font-medium text-fg hover:bg-divider"
          >
            キャンセル
          </button>
          <button
            type="submit"
            disabled={sending}
            className="h-9 rounded-[9px] bg-accent px-4 text-[13px] font-semibold text-white hover:brightness-105 disabled:opacity-60"
          >
            {sending ? "送っています…" : "招待を送る"}
          </button>
        </div>
      </form>
    </div>
  );
}
