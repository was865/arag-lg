"use client";

/** 設定パネル（specs/014-settings）: 外観・回答・アカウントのタブ。 */
import { useState } from "react";
import { Button, ICON } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ListField, ListGroup, ListItem } from "@/components/ui/list";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AccountPanel } from "@/components/auth/account-panel";
import { Icon } from "@/components/icons";
import { useAgentCfg } from "@/hooks/use-agent-cfg";
import { useTweaks } from "@/hooks/use-tweaks";
import { AGENT_DEFAULTS, AGENT_FIELDS, changedCount, type AgentField, type AgentSettings } from "@/lib/agent-settings";
import { ACCENT_PRESETS } from "@/lib/constants";
import { ACCENT_TONES } from "@/lib/accent";
import type { CitationStyle, Density, ToolView } from "@/lib/types";
import { cn } from "@/lib/utils";

export type SettingsTab = "appearance" | "agent" | "account";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "appearance", label: "外観" },
  { id: "agent", label: "回答" },
  { id: "account", label: "アカウント" },
];

const ACCENT_NAMES: Record<string, string> = {
  "#D2402B": "朱",
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

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent title="設定" size="lg" className="h-[min(660px,86vh)] max-md:h-[90dvh]">
        <Tabs value={tab} onValueChange={(v) => setTab(v as SettingsTab)} className="flex min-h-0 flex-1 flex-col">
          <div className="flex justify-center border-b-[0.5px] border-divider px-5 pb-3">
            <TabsList aria-label="設定の種類" className="w-full max-w-[360px]">
              {tabs.map((t) => (
                <TabsTrigger key={t.id} value={t.id}>
                  {t.label}
                  {t.id === "agent" && changed > 0 && (
                    <span aria-label="既定から変更あり" className="h-1.5 w-1.5 rounded-full bg-accent" />
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto bg-bg-2 pb-[env(safe-area-inset-bottom)]">
            <TabsContent value="appearance" className="outline-none">
              <AppearancePanel />
            </TabsContent>
            <TabsContent value="agent" className="outline-none">
              <AgentPanel />
            </TabsContent>
            {showAccount && (
              <TabsContent value="account" className="outline-none">
                <AccountPanel />
              </TabsContent>
            )}
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

// ── 外観 ─────────────────────────────────────────────────────────────────

function AppearancePanel() {
  const { tweaks, setTweak } = useTweaks();
  return (
    <div className="flex flex-col gap-6 px-5 py-5">
      <ListGroup title="表示">
        <ListField label="テーマ">
          <Segmented
            label="テーマ"
            value={tweaks.dark ? "dark" : "light"}
            options={[
              ["light", "ライト"],
              ["dark", "ダーク"],
            ]}
            onChange={(v) => setTweak("dark", v === "dark")}
          />
        </ListField>
        <ListField label="アクセント色">
          <div role="radiogroup" aria-label="アクセント色" className="flex gap-2">
            {ACCENT_PRESETS.map((c) => {
              const on = tweaks.accent.toLowerCase() === c.toLowerCase();
              return (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  aria-label={ACCENT_NAMES[c] ?? c}
                  title={ACCENT_NAMES[c]}
                  onClick={() => setTweak("accent", c)}
                  className={cn(
                    "grid h-6 w-6 place-items-center rounded-full text-white ring-offset-2 ring-offset-surface",
                    on && "ring-2 ring-fg/30",
                  )}
                  // 画面で実際に使う塗り（白い文字が読める濃さ）を見せる
                  style={{ background: ACCENT_TONES[c].ink }}
                >
                  {on && <Icon name="check" size={ICON.sm} />}
                </button>
              );
            })}
          </div>
        </ListField>
        <ListField label="表示の密度">
          <Segmented<Density>
            label="表示の密度"
            value={tweaks.density}
            options={[
              ["comfy", "ゆったり"],
              ["compact", "コンパクト"],
            ]}
            onChange={(v) => setTweak("density", v)}
          />
        </ListField>
      </ListGroup>

      <ListGroup title="回答の表示" footer="外観の設定はこの端末にだけ保存されます。">
        <ListField label="出典の表示" hint="回答内の出典番号の表示形式">
          <Segmented<CitationStyle>
            label="出典の表示"
            value={tweaks.citationStyle}
            options={[
              ["numbered", "番号"],
              ["chip", "チップ"],
              ["pill", "バッジ"],
            ]}
            onChange={(v) => setTweak("citationStyle", v)}
          />
        </ListField>
        <ListField label="実行ステップの表示" hint="検索や読み込みの経過の表示形式">
          <Segmented<ToolView>
            label="実行ステップの表示"
            value={tweaks.toolView}
            options={[
              ["card", "カード"],
              ["timeline", "タイムライン"],
              ["log", "ログ"],
            ]}
            onChange={(v) => setTweak("toolView", v)}
          />
        </ListField>
        <ListField label="思考プロセスを表示" hint="モデルの思考（Thinking）も実行ステップに表示します">
          <Switch
            label="思考プロセスを表示"
            checked={tweaks.showReasoning}
            onChange={(v) => setTweak("showReasoning", v)}
          />
        </ListField>
      </ListGroup>
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
    <div className="flex flex-col gap-6 px-5 py-5">
      <ListGroup footer="この端末から送る質問に使われます。既定から変えた項目だけが送られます。">
        <ListItem>
          <span className="min-w-0 flex-1 text-body text-muted">
            {changed > 0 ? (
              <>
                既定から <span className="font-semibold text-fg">{changed}</span> 項目を変えています
              </>
            ) : (
              "すべて既定の設定です"
            )}
          </span>
          <Button variant="plain" onClick={resetAgentCfg} disabled={changed === 0}>
            既定に戻す
          </Button>
        </ListItem>
      </ListGroup>

      <ListGroup title="検索と回答">
        {basic.map((f) => (
          <AgentRow key={f.key} field={f} cfg={cfg} set={setAgentCfg} />
        ))}
      </ListGroup>

      <details className="group" open={advancedChanged || undefined}>
        <summary className="mb-1.5 flex cursor-pointer list-none items-center gap-1 px-3.5 text-caption font-medium text-muted hover:text-fg [&::-webkit-details-marker]:hidden">
          <Icon name="chevronRight" size={ICON.sm} className="transition-transform group-open:rotate-90" />
          詳細な設定
        </summary>
        <ListGroup>
          {advanced.map((f) => (
            <AgentRow key={f.key} field={f} cfg={cfg} set={setAgentCfg} />
          ))}
        </ListGroup>
      </details>
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
      <ListField label={f.label} badge={f.term} hint={hint} changed={!isDefault}>
        <Switch label={f.label} checked={cfg[f.key]} onChange={(v) => set(f.key, v)} />
      </ListField>
    );
  }
  const v = cfg[f.key];
  const decimals = f.step < 1 ? 2 : 0;
  return (
    <ListField label={f.label} badge={f.term} hint={hint} changed={!isDefault}>
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
        <span className="w-9 text-right font-mono text-footnote text-fg">
          {f.key === "per_document" && v === 0 ? "∞" : v.toFixed(decimals)}
        </span>
      </div>
    </ListField>
  );
}
