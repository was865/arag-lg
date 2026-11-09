"use client";

/** 部門の管理（specs/024 R1〜R3）。作成・名前の変更・削除と、メンバー・部門管理者の割り当て。 */
import { useCallback, useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { useConfirm } from "@/hooks/use-confirm";
import { personLabel, remember, usePeople } from "@/hooks/use-people";
import { accessApi, type DepartmentOut, type DeptMemberOut, type Person } from "@/lib/access/api";
import { ApiError } from "@/lib/chat/api";
import { cn } from "@/lib/utils";

const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

const DEPT_ROLE = { member: "メンバー", manager: "部門管理者" } as const;

export function DepartmentsView() {
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const [depts, setDepts] = useState<DepartmentOut[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    accessApi.departments().then(
      (ds) => {
        if (!alive) return;
        const sorted = [...ds].sort((a, b) => a.name.localeCompare(b.name, "ja"));
        setDepts(sorted);
        setSelected((cur) => (cur && sorted.some((d) => d.id === cur) ? cur : (sorted[0]?.id ?? null)));
      },
      (e: unknown) => {
        if (!alive) return;
        push(errText(e, "部門を取得できませんでした"), "error");
        setDepts((d) => d ?? []);
      },
    );
    return () => {
      alive = false;
    };
  }, [tick, push]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    try {
      const d = await accessApi.createDepartment(name);
      setNewName("");
      setSelected(d.id);
      push(`「${name}」を作りました`, "success");
      reload();
    } catch (err) {
      push(errText(err, "作れませんでした"), "error");
    }
  };

  const current = depts?.find((d) => d.id === selected) ?? null;

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-bg">
      <AdminHeader current="departments">
        {depts && <span className="font-mono text-[11px] text-muted max-md:hidden">{depts.length} 部門</span>}
      </AdminHeader>
      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto grid max-w-[1000px] grid-cols-[240px_minmax(0,1fr)] gap-6 px-[18px] pb-10 pt-4 max-md:grid-cols-1 max-md:gap-4 max-md:px-3">
          <aside className="flex flex-col gap-2">
            <form onSubmit={create} className="flex gap-1.5">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                maxLength={100}
                placeholder="新しい部門の名前"
                aria-label="新しい部門の名前"
                className="h-8 min-w-0 flex-1 rounded-lg border-[0.5px] border-divider-strong bg-surface px-2.5 text-[13px] text-fg outline-none placeholder:text-muted-2 focus:border-accent"
              />
              <button
                type="submit"
                disabled={!newName.trim()}
                aria-label="部門を作る"
                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent text-white hover:brightness-105 disabled:opacity-50"
              >
                <Icon name="plus" size={14} />
              </button>
            </form>
            {depts === null ? (
              <div className="grid h-24 place-items-center">
                <span className="h-5 w-5 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
              </div>
            ) : depts.length === 0 ? (
              <p className="m-0 px-1 py-6 text-[12.5px] leading-[1.6] text-muted">
                まだ部門がありません。「製造部」「品質保証部」のように作ると、ナレッジベースを部門ごとに共有できます。
              </p>
            ) : (
              <nav aria-label="部門" className="flex flex-col gap-0.5 max-md:flex-row max-md:flex-wrap max-md:gap-1">
                {depts.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setSelected(d.id)}
                    aria-current={d.id === selected ? "true" : undefined}
                    className={cn(
                      "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px]",
                      "max-md:rounded-full max-md:border-[0.5px] max-md:border-divider-strong max-md:px-3",
                      d.id === selected ? "bg-surface-2 font-semibold text-fg" : "text-fg-2 hover:bg-divider",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{d.name}</span>
                    <span className="font-mono text-[11px] text-muted">{d.member_count}</span>
                  </button>
                ))}
              </nav>
            )}
          </aside>
          <section className="min-w-0">
            {current ? (
              <DepartmentDetail key={current.id} dept={current} onChanged={reload} confirm={confirm} />
            ) : (
              depts &&
              depts.length > 0 && <p className="py-16 text-center text-[13px] text-muted">部門を選んでください</p>
            )}
          </section>
        </div>
      </div>
      {dialog}
    </div>
  );
}

function DepartmentDetail({
  dept,
  onChanged,
  confirm,
}: {
  dept: DepartmentOut;
  onChanged: () => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const push = useToast();
  const [members, setMembers] = useState<DeptMemberOut[] | null>(null);
  const [name, setName] = useState(dept.name);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const people = usePeople(members?.map((m) => m.user_id) ?? []);

  useEffect(() => {
    let alive = true;
    accessApi.departmentMembers(dept.id).then(
      (ms) => alive && setMembers(ms),
      (e: unknown) => {
        if (!alive) return;
        push(errText(e, "メンバーを取得できませんでした"), "error");
        setMembers([]);
      },
    );
    return () => {
      alive = false;
    };
  }, [dept.id, tick, push]);

  const run = async (fn: () => Promise<unknown>, done: string, fallback: string) => {
    setBusy(true);
    try {
      await fn();
      push(done, "success");
      setTick((t) => t + 1);
      onChanged();
    } catch (e) {
      push(errText(e, fallback), "error");
    } finally {
      setBusy(false);
    }
  };

  const rename = (e: React.FormEvent) => {
    e.preventDefault();
    const n = name.trim();
    if (!n || n === dept.name) return;
    void run(() => accessApi.renameDepartment(dept.id, n), "名前を変えました", "名前を変えられませんでした");
  };

  const remove = async () => {
    const ok = await confirm({
      title: `「${dept.name}」を削除しますか？`,
      description:
        "この部門に共有していたナレッジベースは、部門のメンバーから見えなくなります（個別に共有された人は残ります）。メンバーのアカウントは消えません。",
      confirmLabel: "削除する",
      tone: "danger",
    });
    if (ok) void run(() => accessApi.deleteDepartment(dept.id), `「${dept.name}」を削除しました`, "削除できませんでした");
  };

  const sorted = [...(members ?? [])].sort(
    (a, b) =>
      (a.role === "manager" ? 0 : 1) - (b.role === "manager" ? 0 : 1) ||
      personLabel(a.user_id, people).localeCompare(personLabel(b.user_id, people), "ja"),
  );

  return (
    <div className={cn("flex flex-col gap-4", busy && "opacity-70")}>
      <form onSubmit={rename} className="flex items-center gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
          aria-label="部門の名前"
          className="h-9 min-w-0 flex-1 rounded-lg border-[0.5px] border-transparent bg-transparent px-2 text-[17px] font-bold text-fg outline-none hover:border-divider-strong focus:border-accent"
        />
        {name.trim() !== dept.name && name.trim() && (
          <button
            type="submit"
            disabled={busy}
            className="h-8 rounded-lg bg-accent px-3 text-[12.5px] font-semibold text-white hover:brightness-105"
          >
            保存
          </button>
        )}
        <button
          type="button"
          onClick={() => void remove()}
          disabled={busy}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] text-danger hover:bg-danger-soft"
        >
          <Icon name="trash" size={13} />
          <span className="max-md:hidden">削除</span>
        </button>
      </form>

      <AddMember
        existing={new Set(members?.map((m) => m.user_id) ?? [])}
        disabled={busy}
        onAdd={(p) =>
          void run(
            () => accessApi.putDepartmentMember(dept.id, p.id, "member"),
            `${p.name || p.email} さんを加えました`,
            "加えられませんでした",
          )
        }
      />

      <div>
        <div className="grid grid-cols-[minmax(0,1fr)_130px_32px] gap-3 border-b-[0.5px] border-divider px-2 py-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-2">
          <span>メンバー（{members?.length ?? 0}）</span>
          <span>役割</span>
          <span />
        </div>
        {members === null ? (
          <div className="grid h-24 place-items-center">
            <span className="h-5 w-5 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
          </div>
        ) : members.length === 0 ? (
          <p className="py-10 text-center text-[12.5px] text-muted">まだだれもいません。上の欄から加えてください。</p>
        ) : (
          sorted.map((m) => {
            const p = people.get(m.user_id);
            return (
              <div key={m.user_id} className="grid grid-cols-[minmax(0,1fr)_130px_32px] items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-surface-2">
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">{personLabel(m.user_id, people)}</div>
                  {p?.name && <div className="truncate text-[11.5px] text-muted">{p.email}</div>}
                </div>
                <select
                  value={m.role}
                  disabled={busy}
                  aria-label={`${personLabel(m.user_id, people)} さんの部門での役割`}
                  onChange={(e) => {
                    const role = e.target.value as "member" | "manager";
                    void run(
                      () => accessApi.putDepartmentMember(dept.id, m.user_id, role),
                      `「${DEPT_ROLE[role]}」にしました`,
                      "変えられませんでした",
                    );
                  }}
                  className="h-7 rounded-md border-[0.5px] border-divider-strong bg-surface px-1.5 text-[12px] text-fg"
                >
                  <option value="member">{DEPT_ROLE.member}</option>
                  <option value="manager">{DEPT_ROLE.manager}</option>
                </select>
                <button
                  onClick={() =>
                    void run(
                      () => accessApi.removeDepartmentMember(dept.id, m.user_id),
                      `${personLabel(m.user_id, people)} さんを外しました`,
                      "外せませんでした",
                    )
                  }
                  disabled={busy}
                  aria-label={`${personLabel(m.user_id, people)} さんを部門から外す`}
                  className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
                >
                  <Icon name="close" size={12} />
                </button>
              </div>
            );
          })
        )}
      </div>
      <p className="m-0 px-2 text-[11.5px] leading-[1.6] text-muted">
        部門管理者は、この部門のメンバーを加えたり外したりでき、部門向けのナレッジベースを作れます。ナレッジベースの中身を見られるかどうかは、各ナレッジベースの「共有」で決まります。
      </p>
    </div>
  );
}

/** 名前・メールで探して部門に加える。 */
function AddMember({
  existing,
  disabled,
  onAdd,
}: {
  existing: Set<string>;
  disabled: boolean;
  onAdd: (p: Person) => void;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Person[]>([]);
  const query = q.trim();

  useEffect(() => {
    if (!query) return;
    let alive = true;
    const t = window.setTimeout(() => {
      accessApi.searchPeople(query).then(
        (ps) => {
          remember(ps);
          if (alive) setHits(ps);
        },
        () => undefined,
      );
    }, 200);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [query]);

  const shown = query ? hits.filter((p) => !existing.has(p.id)) : [];
  return (
    <div className="relative">
      <label className="flex h-9 items-center gap-2 rounded-lg border-[0.5px] border-divider-strong bg-surface px-2.5 text-muted focus-within:border-accent">
        <Icon name="plus" size={13} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          disabled={disabled}
          placeholder="名前・メールで探して加える"
          className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-fg outline-none placeholder:text-muted-2"
        />
      </label>
      {shown.length > 0 && (
        <ul className="absolute inset-x-0 top-10 z-20 m-0 max-h-[260px] list-none overflow-y-auto rounded-[10px] border-[0.5px] border-divider-strong bg-surface p-1 shadow-e2">
          {shown.map((p) => (
            <li key={p.id}>
              <button
                onClick={() => {
                  onAdd(p);
                  setQ("");
                  setHits([]);
                }}
                className="flex w-full flex-col items-start rounded-md px-2.5 py-1.5 text-left hover:bg-divider"
              >
                <span className="text-[13px] text-fg">{p.name || p.email}</span>
                {p.name && <span className="text-[11.5px] text-muted">{p.email}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
