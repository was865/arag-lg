"use client";

/**
 * 社内システム（MCP サーバ）の登録と、エージェントに使わせるツール・使える部門の管理（specs/032 R8〜R11）。
 * 書き込みのツール（readOnlyHint の無いもの）は選べない。変更は次の質問から効く。
 */
import { ListSkeleton } from "@/components/ui/skeleton";
import createClient from "openapi-fetch";
import { useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { useToast } from "@/components/feedback/toast-provider";
import { Icon } from "@/components/icons";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { FileTile } from "@/components/ui/file-tile";
import { Field, inputClass } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useConfirm } from "@/hooks/use-confirm";
import { useDepartments } from "@/hooks/use-departments";
import type { components, paths } from "@/lib/api/schema";
import { formatLocalMinute } from "@/lib/datetime";
import { SYSTEM_META } from "@/lib/file-types";
import { cn } from "@/lib/utils";

type Overview = components["schemas"]["McpAdminOut"];
type Server = components["schemas"]["McpServerOut"];
type ShareRow = components["schemas"]["McpShareRow"];
type AuthKind = "none" | "identity" | "bearer";

const client = createClient<paths>({ baseUrl: "/api" });
const ghostBtn = buttonVariants({ variant: "ghost", size: "sm" });

const AUTH_LABEL: Record<AuthKind, string> = {
  identity: "利用者の身元（署名付き）",
  bearer: "固定のトークン",
  none: "認証なし",
};

function errMessage(e: unknown, fallback: string): string {
  const m = (e as { error?: { message?: string } } | undefined)?.error?.message;
  return m ?? fallback;
}

/** 使える範囲の 1 行の表示（全員・部門名）。 */
export function sharesLabel(shares: ShareRow[]): string {
  if (shares.some((s) => s.subject_type === "everyone")) return "全員";
  const names = shares.filter((s) => s.subject_type === "department").map((s) => s.name ?? s.subject_id);
  return names.length ? names.join("・") : "だれも使えない";
}

export function SystemsView() {
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Server | "new" | null>(null);
  const [tools, setTools] = useState<Server | null>(null);
  const [shares, setShares] = useState<Server | null>(null);
  const [checking, setChecking] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const refresh = () => setReload((n) => n + 1);

  useEffect(() => {
    let alive = true;
    client.GET("/v1/admin/mcp-servers").then(({ data: d, error: e }) => {
      if (!alive) return;
      if (d) {
        setData(d);
        setError(null);
      } else setError(errMessage(e, "一覧を読み込めませんでした"));
    });
    return () => {
      alive = false;
    };
  }, [reload]);

  const check = async (s: Server) => {
    setChecking(s.id);
    const { data: r, error: e } = await client.POST("/v1/admin/mcp-servers/{server_id}/refresh", {
      params: { path: { server_id: s.id } },
    });
    setChecking(null);
    if (e || !r) push(errMessage(e, "確認できませんでした"), "error");
    else if (r.check_error) push(`「${s.label}」に接続できませんでした`, "error");
    else push(`「${s.label}」のツールを読み直しました（${r.tools.length} 個）`);
    refresh();
  };

  const toggle = async (s: Server) => {
    const { error: e } = await client.PATCH("/v1/admin/mcp-servers/{server_id}", {
      params: { path: { server_id: s.id } },
      body: { enabled: !s.enabled },
    });
    if (e) push(errMessage(e, "変更できませんでした"), "error");
    refresh();
  };

  const remove = async (s: Server) => {
    const ok = await confirm({
      title: `「${s.label}」の登録を削除しますか？`,
      description: "ツールの選択と使える範囲も消えます。これまでの回答の出典は残ります。",
      confirmLabel: "削除する",
      tone: "danger",
    });
    if (!ok) return;
    const { error: e } = await client.DELETE("/v1/admin/mcp-servers/{server_id}", {
      params: { path: { server_id: s.id } },
    });
    if (e) push(errMessage(e, "削除できませんでした"), "error");
    else push(`「${s.label}」を削除しました`);
    refresh();
  };

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-bg">
      <AdminHeader current="systems">
        <Button variant="primary" size="sm" onClick={() => setEditing("new")}>
          <Icon name="plus" size={13} />
          登録
        </Button>
      </AdminHeader>
      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5 px-[18px] pb-12 pt-4 max-md:px-3">
          {error && <p className="m-0 text-footnote text-danger">{error}</p>}
          {!data && !error && <ListSkeleton rows={4} />}
          {data && !data.identity_ready && (
            <div
              role="alert"
              className="flex gap-2.5 rounded-card border-[0.5px] border-danger/40 bg-danger-soft px-4 py-3 text-footnote leading-[1.7] text-fg-2"
            >
              <span className="mt-0.5 text-danger">
                <Icon name="alert" size={15} />
              </span>
              <div>
                <b className="text-fg">利用者の身元を渡せません。</b>
                署名の鍵 <code className="font-mono">ARAG_MCP_IDENTITY_KEY</code> がサーバに設定されていないため、
                「利用者の身元」で認証するシステムは使われません。鍵を <code className="font-mono">.env</code> に書き、
                API と runner を再起動してください。
              </div>
            </div>
          )}
          {data && (
            <section className="card">
              <div className="px-4 pb-2 pt-3.5">
                <h2 className="m-0 text-callout font-semibold text-fg">社内システム（MCP）</h2>
                <p className="m-0 mt-0.5 text-caption leading-[1.6] text-muted">
                  エージェントが読み取りに使うシステムです。選んだ読み取り専用のツールだけを、使える範囲の部門の人の質問で使います。
                  問い合わせは利用者の身元で行い、見せる行・列はシステムの側で決まります。変更は次の質問から効きます。
                </p>
              </div>
              {data.servers.length === 0 ? (
                <p className="m-0 px-4 pb-5 pt-1 text-footnote text-muted">
                  まだありません。模擬のシステムは <code className="font-mono">make up-mock</code> で起動し、
                  <code className="font-mono">uv run python -m arag.cli mcp-register --mock</code> で登録できます。
                </p>
              ) : (
                <ul className="m-0 list-none p-0">
                  {data.servers.map((s) => {
                    const on = s.tools.filter((t) => t.enabled && t.read_only).length;
                    return (
                      <li
                        key={s.id}
                        className={cn(
                          "flex items-start gap-3 border-t-[0.5px] border-divider px-4 py-2.5 max-md:flex-wrap",
                          !s.enabled && "opacity-60",
                        )}
                      >
                        <FileTile icon={SYSTEM_META.iconName} color={SYSTEM_META.color} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-body font-semibold text-fg">{s.label}</span>
                            <span className="font-mono text-caption text-muted-2">{s.name}</span>
                            {!s.enabled && (
                              <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-caption text-muted">無効</span>
                            )}
                          </div>
                          {s.description && <p className="m-0 mt-0.5 text-caption text-fg-2">{s.description}</p>}
                          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-caption text-muted">
                            <span className="break-all font-mono">{s.url}</span>
                            <span>{AUTH_LABEL[s.auth_kind as AuthKind] ?? s.auth_kind}</span>
                            <span>
                              ツール {on} / {s.tools.length}
                            </span>
                            <span>使える範囲: {sharesLabel(s.shares)}</span>
                          </div>
                          {s.check_error ? (
                            <p className="m-0 mt-1 flex items-start gap-1 break-all text-caption text-danger">
                              <span className="mt-[2px] shrink-0">
                                <Icon name="alert" size={11} />
                              </span>
                              {s.check_error}
                            </p>
                          ) : (
                            s.checked_at && (
                              <p className="m-0 mt-1 flex items-center gap-1 text-caption text-fg-2">
                                <Icon name="check" size={11} />
                                {formatLocalMinute(s.checked_at)} に確認
                              </p>
                            )
                          )}
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1 max-md:w-full max-md:pl-11">
                          <button onClick={() => void check(s)} disabled={checking === s.id} className={ghostBtn}>
                            {checking === s.id ? "確認しています…" : "接続を確認"}
                          </button>
                          <button onClick={() => setTools(s)} className={ghostBtn}>
                            ツール
                          </button>
                          <button onClick={() => setShares(s)} className={ghostBtn}>
                            使える範囲
                          </button>
                          <button role="switch" aria-checked={s.enabled} onClick={() => void toggle(s)} className={ghostBtn}>
                            {s.enabled ? "無効にする" : "有効にする"}
                          </button>
                          <button onClick={() => setEditing(s)} className={ghostBtn}>
                            編集
                          </button>
                          <button
                            onClick={() => void remove(s)}
                            className={cn(ghostBtn, "hover:text-danger")}
                            aria-label={`「${s.label}」を削除`}
                          >
                            削除
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          )}
        </div>
      </div>
      {editing && data && (
        <ServerDialog
          initial={editing === "new" ? null : editing}
          encryptionReady={data.encryption_ready}
          onClose={() => setEditing(null)}
          onSaved={(msg) => {
            setEditing(null);
            push(msg);
            refresh();
          }}
        />
      )}
      {tools && (
        <ToolsDialog
          server={tools}
          onClose={() => setTools(null)}
          onSaved={() => {
            setTools(null);
            push(`「${tools.label}」のツールを保存しました`);
            refresh();
          }}
        />
      )}
      {shares && (
        <SharesDialog
          server={shares}
          onClose={() => setShares(null)}
          onSaved={() => {
            setShares(null);
            push(`「${shares.label}」の使える範囲を保存しました`);
            refresh();
          }}
        />
      )}
      {dialog}
    </div>
  );
}

function Shell({
  title,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  onClose: () => void;
  onSubmit: () => void;
  children: React.ReactNode;
}) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={title} size="sm" className="max-h-[90dvh]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
          className="flex min-h-0 flex-col"
        >
          <DialogBody className="flex flex-col gap-3 pb-1">{children}</DialogBody>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Buttons({ busy, label, onClose }: { busy: boolean; label: string; onClose: () => void }) {
  return (
    <DialogFooter className="px-0 pb-4 pt-2">
      <Button onClick={onClose}>キャンセル</Button>
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "保存しています…" : label}
      </Button>
    </DialogFooter>
  );
}

function ServerDialog({
  initial,
  encryptionReady,
  onClose,
  onSaved,
}: {
  initial: Server | null;
  encryptionReady: boolean;
  onClose: () => void;
  onSaved: (msg: string) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [label, setLabel] = useState(initial?.label ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [auth, setAuth] = useState<AuthKind>((initial?.auth_kind as AuthKind) ?? "identity");
  const [token, setToken] = useState("");
  const [timeout, setTimeoutSec] = useState(initial?.timeout_sec != null ? String(initial.timeout_sec) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const t = timeout.trim() ? Number(timeout) : null;
    if (t !== null && (!Number.isFinite(t) || t < 1 || t > 120)) {
      setError("待つ上限は 1〜120 秒で入力してください");
      return;
    }
    setBusy(true);
    setError(null);
    const tok = token.trim();
    const res = initial
      ? await client.PATCH("/v1/admin/mcp-servers/{server_id}", {
          params: { path: { server_id: initial.id } },
          body: {
            label: label.trim(),
            description: description.trim(),
            url: url.trim(),
            auth_kind: auth,
            timeout_sec: t,
            ...(tok ? { token: tok } : {}),
          },
        })
      : await client.POST("/v1/admin/mcp-servers", {
          body: {
            name: name.trim(),
            label: label.trim(),
            description: description.trim(),
            url: url.trim(),
            auth_kind: auth,
            token: tok || null,
            timeout_sec: t,
            enabled: true,
          },
        });
    setBusy(false);
    if (res.error) setError(errMessage(res.error, "保存できませんでした"));
    else onSaved(initial ? `「${label.trim()}」を保存しました` : `「${label.trim()}」を登録しました。ツールを読み込みました`);
  };

  return (
    <Shell title={initial ? "社内システムを編集" : "社内システムを登録"} onClose={onClose} onSubmit={() => void submit()}>
      <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
        <Field label="表示名">
          <input value={label} required maxLength={100} placeholder="ERP（資材・購買）" onChange={(e) => setLabel(e.target.value)} className={inputClass} />
        </Field>
        <Field label="名前" hint="英小文字・数字・_。ツール名の頭に付きます。">
          <input
            value={name}
            required
            disabled={!!initial}
            spellCheck={false}
            pattern="[a-z][a-z0-9_]{0,31}"
            placeholder="erp"
            onChange={(e) => setName(e.target.value)}
            className={cn(inputClass, "font-mono")}
          />
        </Field>
      </div>
      <Field label="説明（任意）" hint="モデルにも渡します。何が分かるシステムかを 1〜2 文で。">
        <textarea
          value={description}
          rows={2}
          maxLength={1000}
          onChange={(e) => setDescription(e.target.value)}
          className={cn(inputClass, "h-auto py-2")}
        />
      </Field>
      <Field label="URL" hint="Streamable HTTP の口（例: http://mock-systems:8201/mcp）">
        <input
          type="url"
          value={url}
          required
          spellCheck={false}
          onChange={(e) => setUrl(e.target.value)}
          className={cn(inputClass, "font-mono")}
        />
      </Field>
      <Field label="認証">
        <select value={auth} onChange={(e) => setAuth(e.target.value as AuthKind)} className={inputClass}>
          {(Object.keys(AUTH_LABEL) as AuthKind[]).map((k) => (
            <option key={k} value={k}>
              {AUTH_LABEL[k]}
            </option>
          ))}
        </select>
      </Field>
      {auth === "bearer" && (
        <Field
          label="トークン"
          hint={
            !encryptionReady
              ? "暗号化の鍵（ARAG_SECRET_KEY）が無いため保存できません。"
              : initial?.has_token
                ? "保存済みです。変えるときだけ入力してください。"
                : "暗号化して保存し、画面には出しません。"
          }
        >
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={token}
            disabled={!encryptionReady}
            required={!initial?.has_token}
            onChange={(e) => setToken(e.target.value)}
            className={cn(inputClass, "font-mono")}
          />
        </Field>
      )}
      <Field label="待つ上限（秒・任意）" hint="空ならサーバの既定（ARAG_MCP_TIMEOUT_SEC）。">
        <input
          inputMode="decimal"
          value={timeout}
          onChange={(e) => setTimeoutSec(e.target.value)}
          className={cn(inputClass, "w-28 font-mono")}
        />
      </Field>
      {error && <p className="m-0 text-footnote text-danger">{error}</p>}
      <Buttons busy={busy} label={initial ? "保存" : "登録"} onClose={onClose} />
    </Shell>
  );
}

function ToolsDialog({ server, onClose, onSaved }: { server: Server; onClose: () => void; onSaved: () => void }) {
  const [on, setOn] = useState(() => new Set(server.tools.filter((t) => t.enabled && t.read_only).map((t) => t.name)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const { error: e } = await client.PUT("/v1/admin/mcp-servers/{server_id}/tools", {
      params: { path: { server_id: server.id } },
      body: { enabled: [...on] },
    });
    setBusy(false);
    if (e) setError(errMessage(e, "保存できませんでした"));
    else onSaved();
  };

  return (
    <Shell title={`ツール — ${server.label}`} onClose={onClose} onSubmit={() => void submit()}>
      <p className="m-0 text-caption leading-[1.6] text-muted">
        エージェントに使わせるツールを選びます。読み取り専用（readOnlyHint）でないツールは選べません。
      </p>
      {server.tools.length === 0 ? (
        <p className="m-0 text-footnote text-muted">ツールがありません。「接続を確認」で読み直してください。</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {server.tools.map((t) => (
            <li key={t.name} className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-footnote text-fg">{t.name}</span>
                  {!t.read_only && (
                    <span className="rounded-control bg-danger-soft px-1.5 py-0.5 text-caption text-danger">書き込み</span>
                  )}
                </div>
                {t.description && <p className="m-0 mt-0.5 text-caption leading-[1.5] text-muted">{t.description.split("\n")[0]}</p>}
              </div>
              <Switch
                label={`${t.name} を使う`}
                checked={on.has(t.name)}
                disabled={!t.read_only}
                onChange={(v) =>
                  setOn((s) => {
                    const n = new Set(s);
                    if (v) n.add(t.name);
                    else n.delete(t.name);
                    return n;
                  })
                }
              />
            </li>
          ))}
        </ul>
      )}
      {error && <p className="m-0 text-footnote text-danger">{error}</p>}
      <Buttons busy={busy} label="保存" onClose={onClose} />
    </Shell>
  );
}

function SharesDialog({ server, onClose, onSaved }: { server: Server; onClose: () => void; onSaved: () => void }) {
  const { departments } = useDepartments();
  const [everyone, setEveryone] = useState(server.shares.some((s) => s.subject_type === "everyone"));
  const [depts, setDepts] = useState(
    () => new Set(server.shares.filter((s) => s.subject_type === "department").map((s) => s.subject_id)),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const rows: ShareRow[] = everyone
      ? [{ subject_type: "everyone", subject_id: "" }]
      : [...depts].map((id) => ({ subject_type: "department", subject_id: id }));
    const { error: e } = await client.PUT("/v1/admin/mcp-servers/{server_id}/shares", {
      params: { path: { server_id: server.id } },
      body: { shares: rows },
    });
    setBusy(false);
    if (e) setError(errMessage(e, "保存できませんでした"));
    else onSaved();
  };

  return (
    <Shell title={`使える範囲 — ${server.label}`} onClose={onClose} onSubmit={() => void submit()}>
      <p className="m-0 text-caption leading-[1.6] text-muted">
        ここで選んだ部門の人の質問だけで、このシステムを使います。見せる行・列は、システムの側が利用者の身元で決めます。
      </p>
      <div className="flex items-center justify-between gap-3">
        <span className="text-body text-fg">全員</span>
        <Switch label="全員が使う" checked={everyone} onChange={setEveryone} />
      </div>
      {!everyone && (
        <ul className="m-0 flex list-none flex-col gap-2 border-t-[0.5px] border-divider p-0 pt-3">
          {departments.length === 0 && <li className="text-footnote text-muted">部門がありません</li>}
          {departments.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3">
              <span className="text-body text-fg-2">{d.name}</span>
              <Switch
                label={`${d.name} が使う`}
                checked={depts.has(d.id)}
                onChange={(v) =>
                  setDepts((s) => {
                    const n = new Set(s);
                    if (v) n.add(d.id);
                    else n.delete(d.id);
                    return n;
                  })
                }
              />
            </li>
          ))}
        </ul>
      )}
      {error && <p className="m-0 text-footnote text-danger">{error}</p>}
      <Buttons busy={busy} label="保存" onClose={onClose} />
    </Shell>
  );
}
