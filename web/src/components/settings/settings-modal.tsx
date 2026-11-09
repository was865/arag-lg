"use client";

/** 設定パネル（specs/014-settings）: 外観・回答・アカウントのタブ。 */
import { useEffect, useState } from "react";
import { AccountPanel } from "@/components/auth/account-panel";
import { Icon } from "@/components/icons";
import { useAgentCfg } from "@/hooks/use-agent-cfg";
import { useTweaks } from "@/hooks/use-tweaks";
import { AGENT_DEFAULTS, AGENT_FIELDS, changedCount, type AgentField, type AgentSettings } from "@/lib/agent-settings";
import { ACCENT_PRESETS } from "@/lib/constants";
import type { CitationStyle, Density, ToolView } from "@/lib/types";
import { cn } from "@/lib/utils";

export type SettingsTab = "appearance" | "agent" | "account";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "appearance", label: "外観" },
  { id: "agent", label: "回答" },
  { id: "account", label: "アカウント" },
];

const ACCENT_NAMES: Record<string, string> = {
  "#3FA77E": "緑",
  "#D97757": "橙",
  "#3D7EE6": "青",
  "#8B6FE0": "紫",
};

export function SettingsModal({
  onClose,
  initialTab = "appearance",
  showAccount = true,
}: {
  onClose: () => void;
  initialTab?: SettingsTab;
  showAccount?: boolean;
}) {
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  const { cfg } = useAgentCfg();
  const changed = changedCount(cfg);
  const tabs = showAccount ? TABS : TABS.filter((t) => t.id !== "account");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[230] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="設定"
        onClick={(e) => e.stopPropagation()}
        className="flex h-[min(640px,86vh)] w-[600px] max-w-full animate-pop-in flex-col overflow-hidden rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:h-[88dvh] max-md:w-full max-md:rounded-[18px_18px_0_0]"
      >
        <header className="flex items-center gap-2 px-5 pb-2 pt-3.5">
          <h2 className="m-0 flex-1 text-[15px] font-bold text-fg">設定</h2>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </header>
        <div role="tablist" aria-label="設定の種類" className="flex gap-1 border-b-[0.5px] border-divider px-4">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              id={`settings-tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls="settings-panel"
              onClick={() => setTab(t.id)}
              className={cn(
                "-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-2.5 py-2 text-[13px] font-medium",
                tab === t.id ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg",
              )}
            >
              {t.label}
              {t.id === "agent" && changed > 0 && (
                <span aria-label="既定から変更あり" className="h-1.5 w-1.5 rounded-full bg-accent" />
              )}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id="settings-panel"
          aria-labelledby={`settings-tab-${tab}`}
          className="min-h-0 flex-1 overflow-y-auto pb-[env(safe-area-inset-bottom)]"
        >
          {tab === "appearance" && <AppearancePanel />}
          {tab === "agent" && <AgentPanel />}
          {tab === "account" && showAccount && <AccountPanel />}
        </div>
      </div>
    </div>
  );
}

// ── 外観 ─────────────────────────────────────────────────────────────────

function AppearancePanel() {
  const { tweaks, setTweak } = useTweaks();
  return (
    <div className="flex flex-col">
      <Row label="テーマ">
        <Segmented
          label="テーマ"
          value={tweaks.dark ? "dark" : "light"}
          options={[
            ["light", "ライト"],
            ["dark", "ダーク"],
          ]}
          onChange={(v) => setTweak("dark", v === "dark")}
        />
      </Row>
      <Row label="アクセント色">
        <div role="radiogroup" aria-label="アクセント色" className="flex gap-2">
          {ACCENT_PRESETS.map((c) => {
            const on = tweaks.accent.toLowerCase() === c.toLowerCase();
            return (
              <button
                key={c}
                role="radio"
                aria-checked={on}
                aria-label={ACCENT_NAMES[c] ?? c}
                title={ACCENT_NAMES[c]}
                onClick={() => setTweak("accent", c)}
                className={cn(
                  "grid h-7 w-7 place-items-center rounded-full text-white ring-offset-2 ring-offset-surface",
                  on && "ring-2 ring-fg/40",
                )}
                style={{ background: c }}
              >
                {on && <Icon name="check" size={12} />}
              </button>
            );
          })}
        </div>
      </Row>
      <Row label="表示の密度">
        <Segmented<Density>
          label="表示の密度"
          value={tweaks.density}
          options={[
            ["comfy", "ゆったり"],
            ["compact", "コンパクト"],
          ]}
          onChange={(v) => setTweak("density", v)}
        />
      </Row>
      <Row label="出典の表示" hint="回答の中の出典番号の見せ方">
        <Segmented<CitationStyle>
          label="出典の表示"
          value={tweaks.citationStyle}
          options={[
            ["numbered", "番号"],
            ["chip", "チップ"],
            ["pill", "ピル"],
          ]}
          onChange={(v) => setTweak("citationStyle", v)}
        />
      </Row>
      <Row label="検索の経過" hint="回答の前に行った検索や読み込みの見せ方">
        <Segmented<ToolView>
          label="検索の経過"
          value={tweaks.toolView}
          options={[
            ["card", "カード"],
            ["timeline", "タイムライン"],
            ["log", "ログ"],
          ]}
          onChange={(v) => setTweak("toolView", v)}
        />
      </Row>
      <Row label="考えた過程を表示" hint="モデルが途中で書いた考えも経過に含める">
        <Switch
          label="考えた過程を表示"
          checked={tweaks.showReasoning}
          onChange={(v) => setTweak("showReasoning", v)}
        />
      </Row>
      <p className="m-0 px-5 py-3 text-[11.5px] text-muted-2">外観の設定はこの端末にだけ保存されます。</p>
    </div>
  );
}

// ── 回答 ─────────────────────────────────────────────────────────────────

function AgentPanel() {
  const { cfg, setAgentCfg, resetAgentCfg } = useAgentCfg();
  const changed = changedCount(cfg);
  const basic = AGENT_FIELDS.filter((f) => !f.advanced);
  const advanced = AGENT_FIELDS.filter((f) => f.advanced);
  const advancedChanged = advanced.some((f) => cfg[f.key] !== AGENT_DEFAULTS[f.key]);

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b-[0.5px] border-divider bg-surface-2/60 px-5 py-2.5 text-[12px]">
        <span className="min-w-0 flex-1 text-muted">
          {changed > 0 ? (
            <>
              既定から <span className="font-semibold text-fg">{changed}</span> 項目を変えています
            </>
          ) : (
            "すべて既定の設定です"
          )}
        </span>
        <button
          onClick={resetAgentCfg}
          disabled={changed === 0}
          className="h-7 rounded-md px-2.5 text-[12px] font-medium text-fg hover:bg-divider disabled:cursor-default disabled:text-muted-2 disabled:hover:bg-transparent"
        >
          既定に戻す
        </button>
      </div>
      {basic.map((f) => (
        <AgentRow key={f.key} field={f} cfg={cfg} set={setAgentCfg} />
      ))}
      <details className="group border-b-[0.5px] border-divider" open={advancedChanged || undefined}>
        <summary className="flex cursor-pointer list-none items-center gap-1.5 px-5 py-3 text-[12.5px] font-medium text-muted hover:text-fg [&::-webkit-details-marker]:hidden">
          <Icon name="chevronRight" size={12} className="transition-transform group-open:rotate-90" />
          詳細な設定
        </summary>
        {advanced.map((f) => (
          <AgentRow key={f.key} field={f} cfg={cfg} set={setAgentCfg} />
        ))}
      </details>
      <p className="m-0 px-5 py-3 text-[11.5px] text-muted-2">
        この端末から送る質問に使われます。既定から変えた項目だけが送られます。
      </p>
    </div>
  );
}

function AgentRow({
  field: f,
  cfg,
  set,
}: {
  field: AgentField;
  cfg: AgentSettings;
  set: <K extends keyof AgentSettings>(key: K, value: AgentSettings[K]) => void;
}) {
  const isDefault = cfg[f.key] === AGENT_DEFAULTS[f.key];
  const def = AGENT_DEFAULTS[f.key];
  const hint = [f.hint, `既定: ${typeof def === "boolean" ? (def ? "オン" : "オフ") : def}`].filter(Boolean).join(" ");
  if (f.kind === "bool") {
    return (
      <Row label={f.label} term={f.term} termTitle={`agent_cfg.${f.key}`} hint={hint} changed={!isDefault}>
        <Switch label={f.label} checked={cfg[f.key]} onChange={(v) => set(f.key, v)} />
      </Row>
    );
  }
  const v = cfg[f.key];
  const decimals = f.step < 1 ? 2 : 0;
  return (
    <Row label={f.label} term={f.term} termTitle={`agent_cfg.${f.key}`} hint={hint} changed={!isDefault}>
      <div className="flex items-center gap-2.5">
        <input
          type="range"
          min={f.min}
          max={f.max}
          step={f.step}
          value={v}
          aria-label={f.label}
          onChange={(e) => set(f.key, Number(e.target.value))}
          className="w-[150px] accent-[var(--accent)] max-md:w-[120px]"
        />
        <span className="w-9 text-right font-mono text-[12.5px] text-fg">
          {f.key === "per_document" && v === 0 ? "∞" : v.toFixed(decimals)}
        </span>
      </div>
    </Row>
  );
}

// ── 部品 ─────────────────────────────────────────────────────────────────

function Row({
  label,
  term,
  termTitle,
  hint,
  changed,
  children,
}: {
  label: string;
  /** 技術者向けの用語（Top-K など） */
  term?: string;
  termTitle?: string;
  hint?: string;
  changed?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-4 border-b-[0.5px] border-divider px-5 py-3 max-md:flex-wrap max-md:gap-2">
      <div className="min-w-0 flex-1 max-md:basis-full">
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] font-medium text-fg">
          {label}
          {term && (
            <span
              title={termTitle}
              className="rounded-[4px] bg-divider px-1.5 py-px font-mono text-[10.5px] font-normal tracking-[0.01em] text-muted"
            >
              {term}
            </span>
          )}
          {changed && <span aria-label="既定から変更" className="h-1.5 w-1.5 rounded-full bg-accent" />}
        </div>
        {hint && <div className="mt-0.5 text-[11.5px] leading-snug text-muted">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg bg-surface-2 p-0.5">
      {options.map(([v, l]) => (
        <button
          key={v}
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "h-7 whitespace-nowrap rounded-md px-2.5 text-[12px] font-medium",
            value === v ? "bg-surface text-fg shadow-e1" : "text-muted hover:text-fg",
          )}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

function Switch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-[22px] w-[38px] rounded-full transition-colors",
        checked ? "bg-accent" : "bg-divider-strong",
      )}
    >
      <span
        className={cn(
          "absolute top-[3px] h-4 w-4 rounded-full bg-white shadow-e1 transition-[left]",
          checked ? "left-[19px]" : "left-[3px]",
        )}
      />
    </button>
  );
}
