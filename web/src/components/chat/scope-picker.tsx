"use client";

import { Icon } from "@/components/icons";
import { Popover, PopoverContent, PopoverOption, PopoverTrigger } from "@/components/ui/popover";
import { useKbs } from "@/hooks/use-kbs";
import { Switch } from "@/components/ui/switch";
import type { ScopePreset, ScopeValue } from "@/lib/types";
import { useT } from "@/i18n/context";
import { Badge } from "@/components/ui/badge";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 錨定先のボタン（Composer の検索範囲ボタン）。ポップオーバーはこの上に出す */
  children: React.ReactNode;
  value: ScopeValue;
  onChange: (scope: ScopeValue) => void;
  attachmentCount: number;
}

export function ScopePicker({ open, onOpenChange, children, value, onChange, attachmentCount }: Props) {
  const { t } = useT();
  const onClose = () => onOpenChange(false);
  // 旧版のプリセット（全社・Wiki・Slack など）は実在しないデータソースだったので、添付だけを残す
  const presets: ScopePreset[] = [
    { id: "files", label: t.chat.scopeFilesOnly, iconName: "paperclip", desc: t.chat.scopeFilesOnlyDesc, sources: ["uploads"] },
  ];
  // 添付が無いときは選べない項目を出さない
  const scopePresets = attachmentCount > 0 ? presets : [];
  const { kbs } = useKbs();

  // 検索範囲セレクタ用の KB 行: 「全て」 + アクセスできる実 KB。kbId が retrieve に反映される。
  const allKbsScope: ScopeValue = {
    id: "kb:all", label: t.chat.scopeAllKbs, iconName: "folders",
    desc: t.chat.scopeAllKbsDesc, sources: [], kbId: null,
  };
  const kbScope = (kb: { id: string; kind: string; name: string }): ScopeValue => ({
    id: `kb:${kb.id}`,
    label: kb.kind === "personal" ? t.chat.scopePersonalKb : kb.name,
    iconName: kb.kind === "personal" ? "user" : "database",
    sources: [], kbId: kb.id,
  });

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        title={t.chat.scopeHeader}
        className="w-[340px]"
      >
      <div className="overflow-y-auto p-1.5">
        {/* 実検索範囲 = ナレッジベース。ここの選択だけが retrieve の kb_ids に反映される。 */}
        <div className="px-2.5 pb-1 pt-2 eyebrow">{t.chat.scopeKbSection}</div>
        {[{ scope: allKbsScope, archived: false }, ...kbs.map((kb) => ({ scope: kbScope(kb), archived: kb.status === "archived" }))].map(({ scope: s, archived }) => (
          <PopoverOption
            key={s.id}
            selected={value.id === s.id}
            icon={<Icon name={s.iconName} size={15} />}
            label={s.label}
            // archived KB は既定検索から外れるが、明示選択すれば検索される（バックエンドが補完）。
            // 利用者が「なぜ全体検索に出ないか」を理解できるよう状態を明示する。
            badge={archived && <Badge tone="outline">{t.chat.scopeArchivedBadge}</Badge>}
            hint={s.desc}
            onClick={() => { onChange({ ...s, includeArchived: value.includeArchived }); onClose(); }}
          />
        ))}

        <div className="mx-1 my-1.5 h-px bg-divider" />

        {/* アーカイブも検索トグル（KB 検索範囲に作用するため KB セクション直下に置き、
            プリセットでスクロールアウトせず常に見える位置にする）。 */}
        <label className="flex w-full cursor-pointer items-center gap-2.5 rounded-control px-2.5 py-2 hover:bg-divider">
          <Switch
            size="sm"
            label={t.chat.scopeIncludeArchived}
            checked={!!value.includeArchived}
            onChange={(v) => onChange({ ...value, includeArchived: v })}
          />
          <span className="min-w-0 flex-1 truncate text-body font-semibold text-fg">{t.chat.scopeIncludeArchived}</span>
        </label>

        {scopePresets.length > 0 && <div className="mx-1 my-1.5 h-px bg-divider" />}

        {scopePresets.map((p) => {
          const isFiles = p.id === "files";
          const disabled = isFiles && !attachmentCount;
          return (
            <PopoverOption
              key={p.id}
              disabled={disabled}
              selected={value.id === p.id}
              icon={<Icon name={p.iconName} size={15} />}
              label={p.label}
              badge={isFiles && attachmentCount > 0 && <Badge tone="accent">{attachmentCount}</Badge>}
              hint={disabled ? t.chat.noFilesUploaded : p.desc}
              onClick={() => {
                // includeArchived は検索範囲の修飾子なので KB/プリセット選択をまたいで保持する。
                onChange({ ...p, includeArchived: value.includeArchived });
                onClose();
              }}
            />
          );
        })}
      </div>
      </PopoverContent>
    </Popover>
  );
}
