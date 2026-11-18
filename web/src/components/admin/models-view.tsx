"use client";

/** LLM の接続（API キー）とモデル目録（specs/013-llm-keys R8）。 */
import { ListSkeleton } from "@/components/ui/skeleton";
import createClient from "openapi-fetch";
import { useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { useToast } from "@/components/feedback/toast-provider";
import { Icon } from "@/components/icons";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, inputClass } from "@/components/ui/input";
import { useConfirm } from "@/hooks/use-confirm";
import type { components, paths } from "@/lib/api/schema";
import {
  MODEL_EXAMPLE,
  moveId,
  parseKwargs,
  PROVIDER_LABEL,
  PROVIDERS,
  providerLabel,
  slugify,
  validateModelForm,
  type Provider,
  importConnection,
} from "@/lib/admin/llm";
import { cn } from "@/lib/utils";

type Overview = components["schemas"]["LlmAdminOut"];
type Cred = components["schemas"]["CredentialOut"];
type Model = components["schemas"]["ModelRow"];
type Check = components["schemas"]["CheckOut"];

const client = createClient<paths>({ baseUrl: "/api" });

function errMessage(e: unknown, fallback: string): string {
  const m = (e as { error?: { message?: string } } | undefined)?.error?.message;
  return m ?? fallback;
}

const field = inputClass;
const ghostBtn = buttonVariants({ variant: "ghost", size: "sm" });

export function ModelsView() {
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [credDialog, setCredDialog] = useState<Cred | "new" | null>(null);
  const [modelDialog, setModelDialog] = useState<{ row: Model | null; importing?: boolean } | null>(null);
  const [checks, setChecks] = useState<Record<string, Check | "running">>({});
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    client.GET("/v1/admin/llm").then(({ data: d, error: e }) => {
      if (!alive) return;
      if (d) {
        setData(d);
        setError(null);
      } else setError(errMessage(e, "設定を読み込めませんでした"));
    });
    return () => {
      alive = false;
    };
  }, [reload]);
  const refresh = () => setReload((n) => n + 1);

  const removeCred = async (c: Cred) => {
    const ok = await confirm({
      title: `接続「${c.label}」を削除しますか？`,
      description: "保存しているキーも消えます。元に戻せません。",
      confirmLabel: "削除する",
      tone: "danger",
    });
    if (!ok) return;
    const { error: e } = await client.DELETE("/v1/admin/llm/credentials/{cred_id}", {
      params: { path: { cred_id: c.id } },
    });
    if (e) push(errMessage(e, "削除できませんでした"), "error");
    else push(`接続「${c.label}」を削除しました`);
    refresh();
  };

  const removeModel = async (m: Model) => {
    const ok = await confirm({
      title: `モデル「${m.label}」を一覧から削除しますか？`,
      description: "このモデルを選んでいた人は、次の質問から既定のモデルになります。",
      confirmLabel: "削除する",
      tone: "danger",
    });
    if (!ok) return;
    const { error: e } = await client.DELETE("/v1/admin/llm/models/{model_id}", {
      params: { path: { model_id: m.id } },
    });
    if (e) push(errMessage(e, "削除できませんでした"), "error");
    refresh();
  };

  const toggle = async (m: Model) => {
    const { error: e } = await client.PATCH("/v1/admin/llm/models/{model_id}", {
      params: { path: { model_id: m.id } },
      body: { enabled: !m.enabled, clear_credential: false },
    });
    if (e) push(errMessage(e, "変更できませんでした"), "error");
    refresh();
  };

  const move = async (id: string, dir: -1 | 1) => {
    if (!data) return;
    const dbIds = data.models.filter((m) => m.source === "db").map((m) => m.id);
    const next = moveId(dbIds, id, dir);
    if (next === dbIds) return;
    // 先に画面を並べ替える
    setData({
      ...data,
      models: [
        ...next.map((i) => data.models.find((m) => m.source === "db" && m.id === i)!),
        ...data.models.filter((m) => m.source === "env"),
      ],
    });
    const { error: e } = await client.PUT("/v1/admin/llm/models/order", { body: { ids: next } });
    if (e) push(errMessage(e, "並べ替えられませんでした"), "error");
    refresh();
  };

  const check = async (m: Model) => {
    setChecks((c) => ({ ...c, [m.id]: "running" }));
    const { data: r, error: e } = await client.POST("/v1/admin/llm/models/{model_id}/test", {
      params: { path: { model_id: m.id } },
    });
    setChecks((c) => ({
      ...c,
      [m.id]: r ?? { ok: false, latency_ms: 0, error: errMessage(e, "確認できませんでした") },
    }));
  };

  const dbModels = data?.models.filter((m) => m.source === "db") ?? [];
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-bg">
      <AdminHeader current="models" />
      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5 px-[18px] pb-12 pt-4 max-md:px-3">
          {error && <p className="m-0 text-footnote text-danger">{error}</p>}
          {!data && !error && (
            <ListSkeleton rows={4} />
          )}
          {data && (
            <>
              {!data.encryption_ready && (
                <div
                  role="alert"
                  className="flex gap-2.5 rounded-card border-[0.5px] border-danger/40 bg-danger-soft px-4 py-3 text-footnote leading-[1.7] text-fg-2"
                >
                  <span className="mt-0.5 text-danger">
                    <Icon name="alert" size={15} />
                  </span>
                  <div>
                    <b className="text-fg">API キーを登録できません。</b>
                    暗号化の鍵 <code className="font-mono">ARAG_SECRET_KEY</code> がサーバに設定されていません。
                    鍵を作って <code className="font-mono">.env</code> に書き、API とワーカーを再起動してください。
                    <pre className="m-0 mt-1.5 overflow-x-auto rounded-control bg-surface px-2.5 py-1.5 font-mono text-caption">
                      cd api &amp;&amp; uv run python -c &quot;from cryptography.fernet import Fernet;
                      print(Fernet.generate_key().decode())&quot;
                    </pre>
                  </div>
                </div>
              )}

              <section className="card">
                <SectionHead
                  title="接続（API キー）"
                  hint="キーは暗号化して保存し、画面には末尾 4 文字だけを表示します。"
                  action={
                    <Button variant="primary" size="md"
                      onClick={() => setCredDialog("new")}
                      disabled={!data.encryption_ready}
                    >
                      <Icon name="plus" size={12} />
                      接続を追加
                    </Button>
                  }
                />
                {data.credentials.length === 0 ? (
                  <p className="m-0 px-4 pb-5 pt-1 text-footnote text-muted">
                    まだありません。接続を追加しない間は、サーバの環境変数のキーを使います。
                  </p>
                ) : (
                  <ul className="m-0 list-none p-0">
                    {data.credentials.map((c) => (
                      <li
                        key={c.id}
                        className="flex items-center gap-3 border-t-[0.5px] border-divider px-4 py-2.5 max-md:flex-wrap"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                            <span className="break-all text-body font-semibold text-fg">{c.label}</span>
                            <span className="shrink-0 rounded-control bg-surface-2 px-1.5 py-0.5 text-caption text-muted">
                              {providerLabel(c.provider)}
                            </span>
                          </div>
                          <div className="mt-0.5 flex flex-wrap gap-x-3 text-caption text-muted">
                            <span className="font-mono">{c.key_hint ? `••••${c.key_hint}` : "キーなし"}</span>
                            {c.base_url && <span className="truncate font-mono">{c.base_url}</span>}
                            <span>モデル {c.models} 件</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <button onClick={() => setCredDialog(c)} className={ghostBtn}>
                            編集
                          </button>
                          <button
                            onClick={() => void removeCred(c)}
                            className={cn(ghostBtn, "hover:text-danger")}
                            aria-label={`接続「${c.label}」を削除`}
                          >
                            削除
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="card">
                <SectionHead
                  title="モデル一覧"
                  hint="会話で選べるモデルです。使える先頭のものが既定になります。変更は次の質問から効きます。.env のモデルを画面で編集するには「一覧に登録」を押してください。"
                  action={
                    <Button variant="primary" size="md"
                      onClick={() => setModelDialog({ row: null })}
                    >
                      <Icon name="plus" size={12} />
                      モデルを追加
                    </Button>
                  }
                />
                {data.models.length === 0 ? (
                  <p className="m-0 px-4 pb-5 pt-1 text-footnote text-muted">
                    まだありません。モデルを追加すると、会話の入力欄で選べるようになります。
                  </p>
                ) : (
                  <ul className="m-0 list-none p-0">
                    {data.models.map((m) => {
                      const i = dbModels.indexOf(m);
                      const c = checks[m.id];
                      return (
                        <li
                          key={`${m.source}:${m.id}`}
                          className={cn(
                            "flex items-start gap-3 border-t-[0.5px] border-divider px-4 py-2.5 max-md:flex-wrap",
                            !m.enabled && "opacity-60",
                          )}
                        >
                          <div className="flex shrink-0 flex-col pt-0.5">
                            {m.source === "db" ? (
                              <>
                                <button
                                  aria-label={`${m.label} を上へ`}
                                  disabled={i <= 0}
                                  onClick={() => void move(m.id, -1)}
                                  className="grid h-5 w-6 rotate-180 place-items-center rounded text-muted hover:bg-divider hover:text-fg disabled:opacity-25"
                                >
                                  <Icon name="chevronDown" size={11} />
                                </button>
                                <button
                                  aria-label={`${m.label} を下へ`}
                                  disabled={i < 0 || i >= dbModels.length - 1}
                                  onClick={() => void move(m.id, 1)}
                                  className="grid h-5 w-6 place-items-center rounded text-muted hover:bg-divider hover:text-fg disabled:opacity-25"
                                >
                                  <Icon name="chevronDown" size={11} />
                                </button>
                              </>
                            ) : (
                              <span className="w-6" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-body font-semibold text-fg">{m.label}</span>
                              <span className="font-mono text-caption text-muted-2">{m.id}</span>
                              {m.is_default && (
                                <span className="rounded-control bg-accent-soft px-1.5 py-0.5 text-caption font-semibold text-accent">
                                  既定
                                </span>
                              )}
                              {m.source === "env" && (
                                <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-caption text-muted">
                                  .env
                                </span>
                              )}
                              {m.tags.map((t) => (
                                <span
                                  key={t}
                                  className="rounded-control border-[0.5px] border-divider-strong px-1.5 py-[1px] text-caption text-muted"
                                >
                                  {t}
                                </span>
                              ))}
                            </div>
                            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-caption text-muted">
                              <span className="font-mono">{m.model}</span>
                              <span>
                                {m.credential_label ??
                                  (m.source === "env" ? "サーバー設定" : "環境変数のキー")}
                              </span>
                              <Availability model={m} />
                            </div>
                            {c && <CheckResult check={c} />}
                          </div>
                          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1 max-md:w-full max-md:pl-9">
                            <button
                              onClick={() => void check(m)}
                              disabled={c === "running"}
                              className={ghostBtn}
                            >
                              接続を確認
                            </button>
                            {m.source === "db" ? (
                              <>
                                <button
                                  role="switch"
                                  aria-checked={m.enabled}
                                  onClick={() => void toggle(m)}
                                  className={ghostBtn}
                                >
                                  {m.enabled ? "無効にする" : "有効にする"}
                                </button>
                                <button onClick={() => setModelDialog({ row: m })} className={ghostBtn}>
                                  編集
                                </button>
                                <button
                                  onClick={() => void removeModel(m)}
                                  className={cn(ghostBtn, "hover:text-danger")}
                                  aria-label={`モデル「${m.label}」を削除`}
                                >
                                  削除
                                </button>
                              </>
                            ) : (
                              <button
                                onClick={() => setModelDialog({ row: m, importing: true })}
                                className={ghostBtn}
                              >
                                一覧に登録
                              </button>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      </div>

      {credDialog && (
        <CredentialDialog
          initial={credDialog === "new" ? null : credDialog}
          onClose={() => setCredDialog(null)}
          onSaved={(msg) => {
            setCredDialog(null);
            push(msg);
            refresh();
          }}
        />
      )}
      {modelDialog && data && (
        <ModelDialog
          initial={modelDialog.row}
          importing={!!modelDialog.importing}
          credentials={data.credentials}
          onClose={() => setModelDialog(null)}
          onSaved={(msg) => {
            setModelDialog(null);
            push(msg);
            refresh();
          }}
        />
      )}
      {dialog}
    </div>
  );
}

function SectionHead({ title, hint, action }: { title: string; hint: string; action: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 px-4 pb-2 pt-3.5">
      <div className="min-w-0 flex-1">
        <h2 className="m-0 text-callout font-semibold text-fg">{title}</h2>
        <p className="m-0 mt-0.5 text-caption leading-[1.6] text-muted">{hint}</p>
      </div>
      {action}
    </div>
  );
}

function Availability({ model }: { model: Model }) {
  if (!model.enabled) return <span>無効</span>;
  return model.available ? (
    <span className="flex items-center gap-1 text-fg-2">
      <Icon name="check" size={11} />
      使える
    </span>
  ) : (
    <span className="flex items-center gap-1 text-danger">
      <Icon name="alert" size={11} />
      キーが無い・読めない
    </span>
  );
}

function CheckResult({ check }: { check: Check | "running" }) {
  if (check === "running") return <p className="m-0 mt-1 text-caption text-muted">確認しています…</p>;
  return check.ok ? (
    <p className="m-0 mt-1 flex items-center gap-1 text-caption text-fg-2">
      <Icon name="check" size={11} />
      応答がありました（{(check.latency_ms / 1000).toFixed(1)} 秒）
    </p>
  ) : (
    <p className="m-0 mt-1 flex items-start gap-1 break-all text-caption text-danger">
      <span className="mt-[2px] shrink-0">
        <Icon name="alert" size={11} />
      </span>
      {check.error ?? "失敗しました"}
    </p>
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

function CredentialDialog({
  initial,
  onClose,
  onSaved,
}: {
  initial: Cred | null;
  onClose: () => void;
  onSaved: (msg: string) => void;
}) {
  const [provider, setProvider] = useState<Provider>((initial?.provider as Provider) ?? "deepseek");
  const [label, setLabel] = useState(initial?.label ?? "");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const compat = provider === "openai_compatible";

  const submit = async () => {
    setBusy(true);
    setError(null);
    const key = apiKey.trim();
    const res = initial
      ? await client.PATCH("/v1/admin/llm/credentials/{cred_id}", {
          params: { path: { cred_id: initial.id } },
          body: { label: label.trim(), base_url: baseUrl.trim(), ...(key ? { api_key: key } : {}) },
        })
      : await client.POST("/v1/admin/llm/credentials", {
          body: { provider, label: label.trim() || PROVIDER_LABEL[provider], api_key: key || null, base_url: baseUrl.trim() },
        });
    setBusy(false);
    if (res.error) setError(errMessage(res.error, "保存できませんでした"));
    else onSaved(initial ? `接続「${label.trim()}」を保存しました` : "接続を追加しました");
  };

  return (
    <Shell title={initial ? "接続を編集" : "接続を追加"} onClose={onClose} onSubmit={() => void submit()}>
      <Field label="提供元">
        <select
          value={provider}
          disabled={!!initial}
          onChange={(e) => setProvider(e.target.value as Provider)}
          className={field}
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {PROVIDER_LABEL[p]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="名前">
        <input
          value={label}
          maxLength={100}
          placeholder={`${PROVIDER_LABEL[provider]} 本番`}
          onChange={(e) => setLabel(e.target.value)}
          className={field}
        />
      </Field>
      <Field
        label={compat ? "API キー（任意）" : "API キー"}
        hint={initial ? `いまのキー: ${initial.key_hint ? `••••${initial.key_hint}` : "なし"}。変えるときだけ入力してください。` : undefined}
      >
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={apiKey}
          required={!initial && !compat}
          onChange={(e) => setApiKey(e.target.value)}
          className={cn(field, "font-mono")}
        />
      </Field>
      <Field
        label={compat ? "URL" : "URL（任意）"}
        hint={compat ? "例: http://gpu-server:8090/v1" : "プロキシや別のエンドポイントを使う場合のみ入力します。"}
      >
        <input
          type="url"
          value={baseUrl}
          required={compat}
          placeholder={compat ? "http://…/v1" : ""}
          onChange={(e) => setBaseUrl(e.target.value)}
          className={cn(field, "font-mono")}
        />
      </Field>
      {error && <p className="m-0 text-footnote text-danger">{error}</p>}
      <Buttons busy={busy} label={initial ? "保存" : "追加"} onClose={onClose} />
    </Shell>
  );
}

function ModelDialog({
  initial,
  importing,
  credentials,
  onClose,
  onSaved,
}: {
  initial: Model | null;
  importing: boolean;
  credentials: Cred[];
  onClose: () => void;
  onSaved: (msg: string) => void;
}) {
  const editing = !!initial && !importing;
  // .env のモデルは base_url を持つことがある。取り込むときは同じ接続先の接続を使うか作る（落とすと使えなくなる）
  const plan = importing ? importConnection(initial?.base_url, credentials, initial?.label ?? "") : null;
  const [credId, setCredId] = useState<string>(
    initial?.credential_id ??
      (plan && "reuse" in plan ? plan.reuse : importing ? "" : (credentials[0]?.id ?? "")),
  );
  const creating = plan && "create" in plan && !credId ? plan.create : null;
  const cred = credentials.find((c) => c.id === credId) ?? null;
  const provider = (cred?.provider as Provider | undefined) ?? null;
  const [model, setModel] = useState(initial?.model ?? "");
  const [id, setId] = useState(initial?.id ?? "");
  const [idTouched, setIdTouched] = useState(!!initial);
  const [label, setLabel] = useState(initial?.label ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [kwargs, setKwargs] = useState(
    initial && Object.keys(initial.kwargs).length ? JSON.stringify(initial.kwargs, null, 2) : "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    // 作る接続（OpenAI 互換）でも model の接頭辞を確かめる
    const checked: Provider | null = provider ?? (creating ? "openai_compatible" : null);
    const problem = validateModelForm({ id, label, model: model.trim(), provider: checked, kwargs });
    if (problem) {
      setError(problem);
      return;
    }
    const parsed = parseKwargs(kwargs);
    const kw = parsed.ok ? parsed.value : {};
    const tagList = tags
      .split(/[,、]/)
      .map((t) => t.trim())
      .filter(Boolean);
    setBusy(true);
    setError(null);
    let useCred = credId;
    if (creating) {
      const made = await client.POST("/v1/admin/llm/credentials", { body: creating });
      if (made.error || !made.data) {
        setBusy(false);
        setError(errMessage(made.error, "接続を作成できませんでした"));
        return;
      }
      useCred = made.data.id;
    }
    const res = editing
      ? await client.PATCH("/v1/admin/llm/models/{model_id}", {
          params: { path: { model_id: initial.id } },
          body: {
            label: label.trim(),
            model: model.trim(),
            credential_id: credId || null,
            clear_credential: !credId,
            kwargs: kw,
            tags: tagList,
          },
        })
      : await client.POST("/v1/admin/llm/models", {
          body: {
            id,
            label: label.trim(),
            model: model.trim(),
            credential_id: useCred || null,
            kwargs: kw,
            tags: tagList,
            enabled: true,
          },
        });
    setBusy(false);
    if (res.error) setError(errMessage(res.error, "保存できませんでした"));
    else onSaved(editing ? `モデル「${label.trim()}」を保存しました` : `モデル「${label.trim()}」を追加しました`);
  };

  return (
    <Shell
      title={editing ? "モデルを編集" : importing ? "一覧に登録" : "モデルを追加"}
      onClose={onClose}
      onSubmit={() => void submit()}
    >
      <Field
        label="接続"
        hint={
          credId
            ? undefined
            : creating
              ? `接続先 ${creating.base_url} の「OpenAI 互換」接続を作成して使います（キーは不要）。`
              : "サーバーの環境変数にあるキー（DEEPSEEK_API_KEY など）を使います。"
        }
      >
        <select value={credId} onChange={(e) => setCredId(e.target.value)} className={field}>
          {credentials.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}（{providerLabel(c.provider)}）
            </option>
          ))}
          <option value="">{creating ? `新規作成（${creating.base_url}）` : "なし（環境変数のキー）"}</option>
        </select>
      </Field>
      <Field label="モデル" hint="「provider:モデル名」の形です。">
        <input
          value={model}
          required
          spellCheck={false}
          placeholder={provider ? MODEL_EXAMPLE[provider] : "deepseek:deepseek-chat"}
          onChange={(e) => {
            setModel(e.target.value);
            if (!idTouched) setId(slugify(e.target.value));
          }}
          className={cn(field, "font-mono")}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
        <Field label="表示名">
          <input value={label} required maxLength={100} onChange={(e) => setLabel(e.target.value)} className={field} />
        </Field>
        <Field label="id">
          <input
            value={id}
            required
            disabled={!!initial}
            spellCheck={false}
            onChange={(e) => {
              setId(e.target.value);
              setIdTouched(true);
            }}
            className={cn(field, "font-mono")}
          />
        </Field>
      </div>
      <Field label="タグ（任意）" hint="カンマ区切り。会話のモデル選択に表示します（例: 高速, 社内）。">
        <input value={tags} onChange={(e) => setTags(e.target.value)} className={field} />
      </Field>
      <Field label="追加の設定（任意・JSON）" hint='例: {"temperature": 0.3, "max_tokens": 2048}'>
        <textarea
          value={kwargs}
          rows={3}
          spellCheck={false}
          onChange={(e) => setKwargs(e.target.value)}
          className={cn(field, "h-auto py-2 font-mono text-footnote")}
        />
      </Field>
      {error && <p className="m-0 text-footnote text-danger">{error}</p>}
      <Buttons busy={busy} label={editing ? "保存" : "追加"} onClose={onClose} />
    </Shell>
  );
}
