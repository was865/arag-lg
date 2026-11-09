"use client";

/** 回答の設定をこの端末に保存する（specs/014-settings R4）。use-tweaks と同じく localStorage を外部ストアにする。 */
import { useMemo, useSyncExternalStore } from "react";
import { AGENT_DEFAULTS, clampAgentCfg, type AgentSettings } from "@/lib/agent-settings";

const KEY = "arag:agent-cfg";
const EVENT = "arag:agent-cfg";

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
const read = () => {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
};

function parse(raw: string): AgentSettings {
  try {
    return clampAgentCfg(raw ? JSON.parse(raw) : null);
  } catch {
    return AGENT_DEFAULTS;
  }
}

function write(next: AgentSettings | null) {
  try {
    if (next) localStorage.setItem(KEY, JSON.stringify(next));
    else localStorage.removeItem(KEY);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

export function useAgentCfg() {
  const raw = useSyncExternalStore(subscribe, read, () => "");
  const cfg = useMemo(() => parse(raw), [raw]);
  const setAgentCfg = <K extends keyof AgentSettings>(key: K, value: AgentSettings[K]) =>
    write(clampAgentCfg({ ...parse(read()), [key]: value }));
  const resetAgentCfg = () => write(null);
  return { cfg, setAgentCfg, resetAgentCfg };
}
