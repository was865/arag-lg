"use client";

/** user_id → 名前・メールの解決（specs/024）。画面をまたいで同じ人を何度も引かないよう、モジュールで持つ。 */
import { useEffect, useState } from "react";
import { accessApi, type Person } from "@/lib/access/api";

const cache = new Map<string, Person>();

export function remember(people: Person[]): void {
  for (const p of people) cache.set(p.id, p);
}

export function personLabel(id: string, people: Map<string, Person>): string {
  const p = people.get(id);
  return p ? p.name || p.email : "（不明な利用者）";
}

/** ids の人を解決して返す（まだ引いていない人だけ問い合わせる）。 */
export function usePeople(ids: string[]): Map<string, Person> {
  const key = [...new Set(ids)].sort().join(",");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const missing = key ? key.split(",").filter((id) => !cache.has(id)) : [];
    if (missing.length === 0) return;
    let alive = true;
    accessApi.resolvePeople(missing).then(
      (found) => {
        remember(found);
        if (alive) setVersion((v) => v + 1);
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [key]);
  // version は再描画のきっかけ。中身はキャッシュから作る
  void version;
  return new Map(key ? key.split(",").flatMap((id) => (cache.has(id) ? [[id, cache.get(id)!] as const] : [])) : []);
}
