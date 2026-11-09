"use client";

/** 部門の一覧（自分の役割つき）。KB を作れるかの判定と、作る先の候補に使う（specs/024 R9）。 */
import { useCallback, useEffect, useState } from "react";
import { accessApi, type DepartmentOut } from "@/lib/access/api";

export function useDepartments(enabled = true): { departments: DepartmentOut[]; reload: () => void } {
  const [departments, setDepartments] = useState<DepartmentOut[]>([]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    accessApi.departments().then(
      (ds) => alive && setDepartments(ds),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [enabled, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { departments, reload };
}
