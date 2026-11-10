"use client";

/** 共有 KB の共有パネル（specs/024 R4〜R8・R12）。Google ドライブの「共有」と同じ形にする。
 * 権限は共有リストの行からだけ来る。管理できない人には同じリストを読むだけで見せる。 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { personLabel, remember, usePeople } from "@/hooks/use-people";
import { accessApi, type DepartmentOut, type Person } from "@/lib/access/api";
import {
  accessLoss,
  effectiveRoles,
  ROLE_HINT,
  ROLE_LABEL,
  sameShares,
  shareError,
  sortShares,
  type Share,
  type ShareRole,
} from "@/lib/access/shares";
import { ApiError } from "@/lib/chat/api";
import { cn } from "@/lib/utils";

export interface KbShareDialogProps {
  kbId: string;
  kbName: string;
  onClose: () => void;
  /** 保存したあと（KB 一覧の印などを更新する）。 */
  onSaved?: () => void;
}

type Candidate = { kind: "department"; dept: DepartmentOut } | { kind: "user"; person: Person };

const ROLES: ShareRole[] = ["viewer", "editor", "manager"];

export function KbShareDialog({ kbId, kbName, onClose, onSaved }: KbShareDialogProps) {
  const push = useToast();
  const [initial, setInitial] = useState<Share[] | null>(null);
  const [shares, setShares] = useState<Share[]>([]);
  const [deptMembers, setDeptMembers] = useState<Record<string, string[]>>({});
  const [canManage, setCanManage] = useState(false);
  const [departments, setDepartments] = useState<DepartmentOut[]>([]);
  const [everyone, setEveryone] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Person[]>([]);
  const [openDept, setOpenDept] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    Promise.all([accessApi.shares(kbId), accessApi.departments(), accessApi.everyoneIds().catch(() => [])]).then(
      ([s, depts, all]) => {
        if (!alive) return;
        const list = s.shares as Share[];
        setInitial(list);
        setShares(list);
        setDeptMembers(s.department_members);
        setCanManage(s.can_manage);
        setDepartments(depts);
        setEveryone(all);
      },
      (e) => alive && setLoadError(e instanceof ApiError ? e.message : "共有の設定を読み込めませんでした"),
    );
    return () => {
      alive = false;
    };
  }, [kbId]);

  // 人の検索は入力が止まってから
  useEffect(() => {
    const q = query.trim();
    if (!q) return;
    const t = window.setTimeout(() => {
      accessApi.searchPeople(q).then(
        (ps) => {
          remember(ps);
          setFound(ps);
        },
        () => setFound([]),
      );
    }, 200);
    return () => window.clearTimeout(t);
  }, [query]);

  const userIds = useMemo(
    () => [
      ...shares.filter((s) => s.subject_type === "user").map((s) => s.subject_id),
      ...Object.values(deptMembers).flat(),
    ],
    [shares, deptMembers],
  );
  const people = usePeople(userIds);
  const deptName = (id: string) => departments.find((d) => d.id === id)?.name ?? "（削除された部門）";
  const label = (s: Share) =>
    s.subject_type === "everyone" ? "社内の全員" : s.subject_type === "department" ? deptName(s.subject_id) : personLabel(s.subject_id, people);

  const ordered = sortShares(shares, label);
  const total = effectiveRoles(shares, deptMembers, everyone).size;
  const hasEveryone = shares.some((s) => s.subject_type === "everyone");
  const dirty = initial !== null && !sameShares(initial, shares);
  const error = dirty ? shareError(shares) : null;
  const loss = initial ? accessLoss(initial, shares, deptMembers, everyone) : { lost: [], lowered: [] };
  const lossPeople = usePeople([...loss.lost, ...loss.lowered]);

  const q = query.trim().toLowerCase();
  const candidates: Candidate[] = q
    ? [
        ...departments
          .filter((d) => d.name.toLowerCase().includes(q))
          .filter((d) => !shares.some((s) => s.subject_type === "department" && s.subject_id === d.id))
          .map((dept) => ({ kind: "department" as const, dept })),
        ...found
          .filter((p) => !shares.some((s) => s.subject_type === "user" && s.subject_id === p.id))
          .map((person) => ({ kind: "user" as const, person })),
      ].slice(0, 8)
    : [];

  const add = async (c: Candidate) => {
    setQuery("");
    setFound([]);
    if (c.kind === "department") {
      setShares((xs) => [...xs, { subject_type: "department", subject_id: c.dept.id, role: "viewer" }]);
      if (!deptMembers[c.dept.id]) {
        try {
          const ms = await accessApi.departmentMembers(c.dept.id);
          setDeptMembers((m) => ({ ...m, [c.dept.id]: ms.map((x) => x.user_id) }));
        } catch {
          // 人数が出ないだけで、追加はできる
        }
      }
    } else {
      setShares((xs) => [...xs, { subject_type: "user", subject_id: c.person.id, role: "viewer" }]);
    }
    inputRef.current?.focus();
  };
  const setRole = (s: Share, role: ShareRole) =>
    setShares((xs) => xs.map((x) => (x.subject_type === s.subject_type && x.subject_id === s.subject_id ? { ...x, role } : x)));
  const remove = (s: Share) =>
    setShares((xs) => xs.filter((x) => !(x.subject_type === s.subject_type && x.subject_id === s.subject_id)));

  const save = async () => {
    if (error || saving) return;
    // 狭めるときは、見られなくなる人を出して確かめる（R8）
    if ((loss.lost.length > 0 || loss.lowered.length > 0) && !confirming) {
      setConfirming(true);
      return;
    }
    setSaving(true);
    try {
      const res = await accessApi.putShares(kbId, shares);
      setInitial(res.shares as Share[]);
      setShares(res.shares as Share[]);
      setDeptMembers(res.department_members);
      setConfirming(false);
      push("共有を保存しました", "success");
      onSaved?.();
      onClose();
    } catch (e) {
      push(e instanceof ApiError ? e.message : "共有を保存できませんでした", "error");
    } finally {
      setSaving(false);
    }
  };

  const names = (ids: string[]) => {
    const shown = ids.slice(0, 5).map((id) => personLabel(id, lossPeople));
    return shown.join("、") + (ids.length > shown.length ? ` ほか ${ids.length - shown.length} 名` : "");
  };

  return (
    <div
      className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`「${kbName}」を共有`}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[min(640px,90dvh)] w-[520px] max-w-full animate-pop-in flex-col rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0]"
      >
        <div className="flex items-start gap-2 px-5 pb-3 pt-5">
          <div className="min-w-0 flex-1">
            <h3 className="m-0 truncate text-[15px] font-bold text-fg">「{kbName}」を共有</h3>
            <p className="m-0 mt-0.5 text-[12px] text-muted">
              {initial === null ? "読み込んでいます…" : `利用できる人: 合計 ${total.toLocaleString("ja-JP")} 名`}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </div>

        {loadError ? (
          <p className="m-0 px-5 pb-5 text-[13px] text-danger">{loadError}</p>
        ) : (
          <>
            {canManage && (
              <div className="relative px-5 pb-2">
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="部門または人（名前・メール）を追加"
                  aria-label="部門または人を追加"
                  className="h-9 w-full rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 text-[13px] text-fg outline-none placeholder:text-muted-2 focus:border-accent"
                />
                {candidates.length > 0 && (
                  <ul
                    role="listbox"
                    className="absolute inset-x-5 top-10 z-10 m-0 list-none overflow-hidden rounded-[10px] border-[0.5px] border-divider-strong bg-surface p-1 shadow-e2"
                  >
                    {candidates.map((c) => (
                      <li key={c.kind === "department" ? `d:${c.dept.id}` : `u:${c.person.id}`}>
                        <button
                          onClick={() => void add(c)}
                          className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] hover:bg-divider"
                        >
                          <Icon name={c.kind === "department" ? "group" : "user"} size={14} className="text-muted" />
                          <span className="min-w-0 flex-1 truncate text-fg">
                            {c.kind === "department" ? c.dept.name : c.person.name || c.person.email}
                          </span>
                          <span className="shrink-0 truncate text-[11.5px] text-muted">
                            {c.kind === "department" ? `部門 · ${c.dept.member_count} 名` : c.person.email}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <ul className="m-0 min-h-0 flex-1 list-none overflow-y-auto px-5 py-1">
              {ordered.map((s) => {
                const key = `${s.subject_type}:${s.subject_id}`;
                const members = s.subject_type === "department" ? (deptMembers[s.subject_id] ?? []) : [];
                const icon: IconName = s.subject_type === "everyone" ? "building" : s.subject_type === "department" ? "group" : "user";
                const sub =
                  s.subject_type === "everyone"
                    ? `社内の ${everyone.length.toLocaleString("ja-JP")} 名`
                    : s.subject_type === "department"
                      ? `部門 · ${members.length} 名`
                      : (people.get(s.subject_id)?.email ?? "人");
                return (
                  <li key={key} className="border-b-[0.5px] border-divider last:border-b-0">
                    <div className="flex items-center gap-2.5 py-2">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-2 text-muted">
                        <Icon name={icon} size={14} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] text-fg">{label(s)}</div>
                        {s.subject_type === "department" ? (
                          <button
                            onClick={() => setOpenDept((d) => (d === s.subject_id ? null : s.subject_id))}
                            aria-expanded={openDept === s.subject_id}
                            className="inline-flex items-center gap-0.5 text-[11.5px] text-muted hover:text-fg"
                          >
                            {sub}
                            <Icon
                              name="chevronDown"
                              size={10}
                              className={cn("transition-transform", openDept === s.subject_id && "rotate-180")}
                            />
                          </button>
                        ) : (
                          <div className="truncate text-[11.5px] text-muted">{sub}</div>
                        )}
                      </div>
                      {canManage ? (
                        <>
                          <select
                            value={s.role}
                            onChange={(e) => setRole(s, e.target.value as ShareRole)}
                            aria-label={`${label(s)} の役割`}
                            title={ROLE_HINT[s.role]}
                            className="h-8 rounded-md border-[0.5px] border-divider-strong bg-surface px-2 text-[12.5px] text-fg"
                          >
                            {(s.subject_type === "everyone" ? (["viewer"] as ShareRole[]) : ROLES).map((r) => (
                              <option key={r} value={r}>
                                {ROLE_LABEL[r]}
                              </option>
                            ))}
                          </select>
                          <button
                            onClick={() => remove(s)}
                            aria-label={`${label(s)} を削除`}
                            className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
                          >
                            <Icon name="close" size={12} />
                          </button>
                        </>
                      ) : (
                        <span className="shrink-0 text-[12.5px] text-muted">{ROLE_LABEL[s.role]}</span>
                      )}
                    </div>
                    {openDept === s.subject_id && (
                      <p className="m-0 pb-2 pl-[42px] text-[12px] leading-[1.6] text-muted">
                        {members.length === 0 ? "メンバーはいません" : members.map((id) => personLabel(id, people)).join("、")}
                      </p>
                    )}
                  </li>
                );
              })}
              {canManage && initial !== null && !hasEveryone && (
                <li className="flex items-center gap-2.5 py-2">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-muted-2">
                    <Icon name="building" size={14} />
                  </span>
                  <span className="min-w-0 flex-1 text-[13px] text-muted">社内の全員</span>
                  <button
                    onClick={() => setShares((xs) => [...xs, { subject_type: "everyone", subject_id: "", role: "viewer" }])}
                    className="rounded-md px-2 py-1 text-[12px] font-medium text-accent hover:bg-accent-soft"
                  >
                    全員に閲覧を許可
                  </button>
                </li>
              )}
            </ul>

            {(error || confirming) && (
              <div
                role="alert"
                className={cn(
                  "mx-5 mt-1 rounded-lg px-3 py-2 text-[12px] leading-[1.6]",
                  error ? "bg-danger-soft text-danger" : "border-[0.5px] border-divider-strong bg-surface-2 text-fg",
                )}
              >
                {error ??
                  [
                    loss.lost.length > 0 && `${loss.lost.length} 名が見られなくなります（${names(loss.lost)}）。`,
                    loss.lowered.length > 0 && `${loss.lowered.length} 名の役割が下がります（${names(loss.lowered)}）。`,
                    "よければもう一度「保存」を押してください。",
                  ]
                    .filter(Boolean)
                    .join(" ")}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 px-5 pb-4 pt-3 max-md:pb-[max(16px,env(safe-area-inset-bottom))]">
              {canManage ? (
                <>
                  <button
                    onClick={onClose}
                    className="h-8 rounded-lg border-[0.5px] border-divider-strong px-3 text-[12.5px] font-medium text-fg hover:bg-divider"
                  >
                    キャンセル
                  </button>
                  <button
                    onClick={() => void save()}
                    disabled={!dirty || Boolean(error) || saving}
                    className="h-8 rounded-lg bg-accent px-3.5 text-[12.5px] font-semibold text-white hover:brightness-105 disabled:opacity-50"
                  >
                    {saving ? "保存しています…" : "保存"}
                  </button>
                </>
              ) : (
                <p className="m-0 flex-1 text-[12px] text-muted">共有を変えられるのは、このナレッジベースの管理者と管理者権限のある人です。</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
