"use client";

/** メンバー管理（specs/010-admin-members）。一覧・招待・役割の変更・停止と再開。 */
import { ListSkeleton } from "@/components/ui/skeleton";
import { useCallback, useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { MemberAccessDialog } from "@/components/admin/member-access-dialog";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { Button, IconButton } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, SearchField, Select } from "@/components/ui/input";
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
        {data && <span className="font-mono text-caption text-muted max-md:hidden">{data.items.length} 人</span>}
        <Button variant="primary" size="sm"
          onClick={() => setInviting(true)}
        >
          <Icon name="plus" size={13} />
          招待
        </Button>
      </AdminHeader>

      <div className="border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <SearchField
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onClear={() => setQuery("")}
          placeholder="名前・メールで探す"
          className="mx-auto max-w-[1000px]"
        />
      </div>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto my-4 w-[calc(100%-36px)] max-w-[1000px] rounded-card border-[0.5px] border-divider-strong bg-surface px-3 pb-3 pt-1 shadow-e1 max-md:my-2 max-md:w-[calc(100%-16px)] max-md:px-1.5">
          <div className="grid grid-cols-[minmax(0,1fr)_130px_80px_70px_32px] gap-3 border-b-[0.5px] border-divider px-2 py-2 text-caption font-semibold uppercase tracking-[0.05em] text-muted-2 max-md:hidden">
            <span>名前</span>
            <span>役割</span>
            <span>状態</span>
            <span className="text-right">登録日</span>
            <span />
          </div>
          {data === null ? (
            <ListSkeleton />
          ) : data.items.length === 0 ? (
            <p className="py-16 text-center text-body text-muted">条件に合うメンバーはいません</p>
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
                    "grid grid-cols-[minmax(0,1fr)_130px_80px_70px_32px] items-center gap-3 rounded-control px-2 py-2 hover:bg-surface-2",
                    "max-md:grid-cols-[minmax(0,1fr)_auto_32px] max-md:gap-2",
                    busy === m.id && "opacity-60",
                  )}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-caption font-bold text-accent">
                      {initialsOf(m.name, m.email)}
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-body font-medium text-fg">
                        {m.name || "（名前なし）"}
                        {me && <span className="ml-1.5 text-caption font-normal text-muted">（あなた）</span>}
                      </div>
                      <div className="truncate text-caption text-muted">
                        {m.email}
                        <span className={cn("hidden max-md:inline", STATUS_TONE[st])}> · {STATUS_LABEL[st]}</span>
                      </div>
                    </div>
                  </div>
                  <div>
                    {canRole ? (
                      <Select
                        value={m.role}
                        disabled={busy === m.id}
                        aria-label={`${m.name || m.email} さんの役割`}
                        onChange={(e) =>
                          void patch(m, { role: e.target.value }, `役割を「${ROLE_LABEL[e.target.value as Role]}」にしました`)
                        }
                        size="sm"
                      >
                        {ASSIGNABLE_ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABEL[r]}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <span className="text-footnote text-fg-2">{ROLE_LABEL[m.role as Role] ?? m.role}</span>
                    )}
                  </div>
                  <span className={cn("text-footnote max-md:hidden", STATUS_TONE[st])}>{STATUS_LABEL[st]}</span>
                  <span className="text-right font-mono text-caption text-muted max-md:hidden">{formatDate(m.createdAt)}</span>
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
          <p className="m-0 mt-4 px-2 text-caption leading-[1.6] text-muted">
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
  return (
    <span className="justify-self-end">
      <Menu>
        <MenuTrigger asChild>
          <IconButton label="操作" icon="more" tooltip={false} disabled={disabled} className="disabled:invisible" />
        </MenuTrigger>
        <MenuContent align="end">
          <MenuItem icon="database" onSelect={onAccess}>
            閲覧できるナレッジベース
          </MenuItem>
          {canResend && (
            <MenuItem icon="mail" onSelect={onResend}>
              パスワード設定のリンクを送る
            </MenuItem>
          )}
          {!canBan ? null : banned ? (
            <MenuItem icon="refresh" onSelect={onUnban}>
              再開する
            </MenuItem>
          ) : (
            <MenuItem icon="lock" danger onSelect={onBan}>
              停止する
            </MenuItem>
          )}
        </MenuContent>
      </Menu>
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

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="メンバーを招待" description="パスワードを設定するリンクをメールで送ります（1 時間有効）。" size="sm">
        <form onSubmit={(e) => void submit(e)} className="flex min-h-0 flex-col">
          <DialogBody className="flex flex-col gap-3 pb-1">
            <Field label="メールアドレス">
              <Input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="名前">
              <Input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="役割">
              <Select
                value={role}
                onChange={(e) => setRole(e.target.value as "member" | "admin")}
                className="w-full"
              >
                <option value="member">メンバー</option>
                {canInviteAdmin && <option value="admin">管理者</option>}
              </Select>
            </Field>
            {error && <p className="m-0 text-footnote text-danger">{error}</p>}
          </DialogBody>
          <DialogFooter>
            <Button onClick={onClose}>キャンセル</Button>
            <Button type="submit" variant="primary" disabled={sending}>
              {sending ? "送っています…" : "招待を送る"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
