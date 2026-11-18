"use client";

import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";
import { DEFAULT_ACCENT, THEME_COLOR_DARK, THEME_COLOR_LIGHT, THEME_STORAGE_KEY } from "@/lib/constants";
import type { Tweaks } from "@/lib/types";
import { migrateStoredTweaks } from "@/lib/tweaks-migrate";
import { accentVars } from "@/lib/accent";

const DEFAULTS: Tweaks = {
  dark: false,
  accent: DEFAULT_ACCENT,
  toolView: "card",
  density: "comfy",
  citationStyle: "numbered",
  showReasoning: false,
};

const TWEAK_EVENT = "arag:tweaks";

// ── External store backed by localStorage (SSR-safe via useSyncExternalStore) ─
function subscribe(onChange: () => void) {
  window.addEventListener(TWEAK_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(TWEAK_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
// Return the raw string so the snapshot reference stays stable between reads.
const getSnapshot = () => localStorage.getItem(THEME_STORAGE_KEY) ?? "";
const getServerSnapshot = () => "";

/** Applies theme class + accent vars to <html> (DOM only — no React state). */
function applyToRoot(t: Tweaks) {
  const el = document.documentElement;
  el.classList.toggle("theme-dark", t.dark);
  el.classList.toggle("theme-light", !t.dark);
  for (const [name, value] of Object.entries(accentVars(t.accent))) {
    if (value) el.style.setProperty(name, value);
    else el.style.removeProperty(name);
  }
  // 首ページの背景の 2 色目。常磐のときは朱、ほかは常磐
  const alt = t.accent.toLowerCase() === "#438067" ? "#D2402B" : "#438067";
  el.style.setProperty("--accent-alt-glow", `color-mix(in srgb, ${alt} 30%, transparent)`);
  // standalone PWA のステータスバー背景（theme-color meta）をテーマに追従させる。
  // meta は layout の themeBootstrap が first paint 前に挿入済み（無ければ作る）。
  let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }
  meta.content = t.dark ? THEME_COLOR_DARK : THEME_COLOR_LIGHT;
}

/** Persisted display preferences (theme/accent/tool view/density/citation style). */
export function useTweaks() {
  const raw = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const tweaks = useMemo<Tweaks>(() => {
    try {
      return { ...DEFAULTS, ...(raw ? migrateStoredTweaks(JSON.parse(raw)) : {}) };
    } catch {
      return DEFAULTS;
    }
  }, [raw]);

  // Keep <html> in sync with the active tweaks (decorative alt-glow isn't set by
  // the layout bootstrap script). DOM-only, so no cascading renders.
  useEffect(() => {
    applyToRoot(tweaks);
  }, [tweaks]);

  const setTweak = useCallback(
    <K extends keyof Tweaks>(key: K, value: Tweaks[K]) => {
      const current = (() => {
        try {
          return { ...DEFAULTS, ...migrateStoredTweaks(JSON.parse(localStorage.getItem(THEME_STORAGE_KEY) || "{}")) } as Tweaks;
        } catch {
          return DEFAULTS;
        }
      })();
      const next = { ...current, [key]: value };
      try {
        localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(next));
      } catch {}
      applyToRoot(next);
      window.dispatchEvent(new Event(TWEAK_EVENT));
    },
    [],
  );

  return { tweaks, setTweak };
}
