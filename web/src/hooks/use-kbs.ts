"use client";

/** アクセス可能 KB（ナレッジベース）一覧の共有ストア。
 *
 * コンポーネントごとに個別フェッチすると KB の作成・削除が他画面（サイドバー等）へ
 * 伝播しないため、モジュール単位の単一キャッシュを useSyncExternalStore で全購読者に
 * 共有する。KB を変更した側は refreshKbs() を呼べば購読中の全 UI に即時反映される。
 *
 * マルチユーザー安全性:
 * - generation によるリクエスト代際保護（旧ユーザーの遅延レスポンスが新ユーザーの state を汚さない）
 * - clearKbsForUserSwitch() で認証境界の即時クリア
 * - /api/v1/kbs 失敗時は前回値を保持せず空 state にする（別ユーザー KB の誤表示防止）
 */

import { useSyncExternalStore } from "react";

export interface KbInfo {
  id: string;
  kind: "personal" | "team" | "org" | string;
  name: string;
  canWrite: boolean;
  /** 紐づくチーム ID（team KB のみ。管理 UI の team-admin 判定に使う）。 */
  teamId: string | null;
  /** KB 内の文書数（rag /kbs の document_count）。 */
  documentCount: number;
  /** KB の状態（"active" | "archived"）。 */
  status: string;
  /** 論理削除時刻（ISO 文字列）。null は生存中。 */
  deletedAt: string | null;
  /** 物理削除（GC）予定時刻（ISO 文字列）。deletedAt + 保持期間。生存中は null。 */
  expiresAt: string | null;
}

interface KbStoreState {
  kbs: KbInfo[];
  loaded: boolean;
}

let state: KbStoreState = { kbs: [], loaded: false };
const listeners = new Set<() => void>();
let inflight: Promise<void> | null = null;
let generation = 0;

function emit() {
  for (const l of listeners) l();
}

/** ユーザー切替時にストアを安全にクリアする。
 *  - generation を進めて進行中の旧リクエストを無効化
 *  - state を空にして全購読者へ即時通知
 *  - inflight を破棄して再取得を許可 */
export function clearKbsForUserSwitch(): void {
  generation += 1;
  inflight = null;
  state = { kbs: [], loaded: false };
  emit();
}

function mapKbRows(rows: unknown[]): KbInfo[] {
  return rows.map((r) => {
    const row = r as Record<string, unknown>;
    return {
    id: row.id as string,
    kind: row.kind as string,
    name: row.name as string,
    canWrite: Boolean(row.writable ?? row.can_write),
    teamId: (row.team_id as string) ?? null,
    documentCount: Number(row.document_count ?? 0),
    status: (row.status as string) ?? "active",
    deletedAt: (row.deleted_at as string) ?? null,
    expiresAt: (row.expires_at as string) ?? null,
  };})
}

async function fetchKbs(requestGeneration: number): Promise<void> {
  try {
    const res = await fetch("/api/v1/kbs", { cache: "no-store" });
    // レスポンスが返る前にユーザーが切り替わっていたら破棄。
    if (requestGeneration !== generation) return;

    const rows: unknown = res.ok ? await res.json() : null;
    if (requestGeneration !== generation) return;

    if (!Array.isArray(rows)) {
      // 取得失敗時は前回値を保持せず空にする（別ユーザーの KB を表示しない）。
      state = { kbs: [], loaded: false };
      emit();
      return;
    }
    state = { loaded: true, kbs: mapKbRows(rows) };
    emit();
  } catch {
    // ネットワークエラー時も空 state に倒す（別ユーザー KB を表示しない）。
    if (requestGeneration !== generation) return;
    state = { kbs: [], loaded: false };
    emit();
  }
}

/** KB 一覧を再取得して全購読者へ反映する（KB 作成・アップロード完了・削除後に呼ぶ）。
 *  同一 generation 内では inflight を共有して重複リクエストを防ぐ。 */
export function refreshKbs(): Promise<void> {
  if (!inflight) {
    const g = generation;
    inflight = fetchKbs(g).finally(() => {
      // generation が進んでいたら inflight をクリアしない（clearKbsForUserSwitch が
      // すでに null にしているので二重解放は起きないが、防御的に確認する）。
      if (generation === g) inflight = null;
    });
  }
  return inflight;
}

function subscribe(listener: () => void): () => void {
  // 最初の購読（再ログインや Storybook のストーリー切替を含む）で必ず取り直す。
  const first = listeners.size === 0;
  listeners.add(listener);
  if (first || !state.loaded) void refreshKbs();
  return () => {
    listeners.delete(listener);
    // 全購読者が消えたら破棄（別ユーザーでの再ログイン時に前ユーザーの KB を見せない）。
    if (listeners.size === 0) state = { kbs: [], loaded: false };
  };
}

const getSnapshot = () => state;
// SSR では空スナップショット（クライアントマウント後に取得）。
const getServerSnapshot = () => state;

export function useKbs(): { kbs: KbInfo[]; writableKbs: KbInfo[] } {
  const s = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return { kbs: s.kbs, writableKbs: s.kbs.filter((k) => k.canWrite) };
}
