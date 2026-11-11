"use client";

/** UI 部品の見本帳。ライトとダークを左右に並べ、段階（文字・角丸・アイコン）と部品を一度に確認する。 */
import { useState } from "react";
import { Icon } from "@/components/icons";
import { ConfirmModal } from "@/components/modals/confirm-modal";
import { SettingsModal } from "@/components/settings/settings-modal";
import { Button, ICON, IconButton } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { OptionBadge, Popover, PopoverContent, PopoverOption, PopoverTrigger } from "@/components/ui/popover";
import { ListField, ListGroup, ListItem } from "@/components/ui/list";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const TYPE = [
  ["text-title", "タイトル 19", "ナレッジベース"],
  ["text-headline", "見出し 15", "設定"],
  ["text-callout", "チャット本文 14", "MX-17 の保証期間は納品日から 12 か月です。"],
  ["text-body", "本文 13", "表示名・パスワード・ログイン中の端末"],
  ["text-footnote", "補助 12.5", "3 件の資料 · 2 分前に更新"],
  ["text-caption", "注記 11.5", "外観の設定はこの端末にだけ保存されます。"],
] as const;

const RADIUS = [
  ["rounded-control", "control 8", "ボタン・入力"],
  ["rounded-card", "card 12", "一覧・カード"],
  ["rounded-sheet", "sheet 16", "ダイアログ"],
] as const;

export function Gallery() {
  const [settings, setSettings] = useState(false);
  const [confirm, setConfirm] = useState(false);
  return (
    <div className="min-h-full bg-bg text-fg">
      <header className="flex flex-wrap items-center gap-3 border-b-[0.5px] border-divider px-6 py-4">
        <h1 className="m-0 flex-1 text-title font-semibold tracking-[-0.01em]">UI 部品</h1>
        <Button onClick={() => setConfirm(true)}>確認ダイアログ</Button>
        <Button variant="primary" onClick={() => setSettings(true)}>
          設定を開く
        </Button>
      </header>
      <div className="grid grid-cols-2 max-wide:grid-cols-1">
        <Board theme="theme-light" />
        <Board theme="theme-dark" />
      </div>
      {settings && <SettingsModal onClose={() => setSettings(false)} />}
      <ConfirmModal
        open={confirm}
        title="このスレッドを削除しますか？"
        description={"削除したスレッドはごみ箱に 30 日間残ります。\nごみ箱から元に戻せます。"}
        confirmLabel="削除"
        tone="danger"
        onConfirm={() => setConfirm(false)}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}

function Board({ theme }: { theme: "theme-light" | "theme-dark" }) {
  const [seg, setSeg] = useState<"numbered" | "chip" | "pill">("numbered");
  const [on, setOn] = useState(true);
  return (
    <section className={cn(theme, "flex flex-col gap-8 bg-bg-2 px-6 py-6 text-fg")}>
      <p className="m-0 text-caption font-medium uppercase tracking-[0.06em] text-muted">
        {theme === "theme-light" ? "ライト" : "ダーク"}
      </p>

      <Block title="文字の段階（6 段）">
        <div className="flex flex-col gap-2.5">
          {TYPE.map(([cls, name, sample]) => (
            <div key={cls} className="flex items-baseline gap-4">
              <code className="w-24 shrink-0 font-mono text-caption text-muted">{name}</code>
              <span className={cn(cls, "min-w-0 truncate")}>{sample}</span>
            </div>
          ))}
        </div>
      </Block>

      <Block title="角丸（3 段）・アイコン（3 段）">
        <div className="flex flex-wrap items-end gap-4">
          {RADIUS.map(([cls, name, use]) => (
            <div key={cls} className="flex flex-col items-center gap-1.5">
              <div className={cn(cls, "h-14 w-20 border-[0.5px] border-divider-strong bg-surface shadow-e1")} />
              <code className="font-mono text-caption text-muted">{name}</code>
              <span className="text-caption text-muted-2">{use}</span>
            </div>
          ))}
          <div className="ml-auto flex items-end gap-4 text-fg">
            {Object.entries(ICON).map(([k, s]) => (
              <div key={k} className="flex flex-col items-center gap-1.5">
                <Icon name="search" size={s} />
                <code className="font-mono text-caption text-muted">
                  {k} {s}
                </code>
              </div>
            ))}
          </div>
        </div>
      </Block>

      <Block title="ボタン">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary">保存</Button>
            <Button>キャンセル</Button>
            <Button variant="ghost">
              <Icon name="plus" size={ICON.md} />
              追加
            </Button>
            <Button variant="danger">削除</Button>
            <Button variant="plain">変更…</Button>
            <IconButton label="閉じる" icon="close" iconSize={ICON.sm} />
            <IconButton label="その他" icon="more" />
            <IconButton size="icon-sm" label="追加" icon="plus" iconSize={ICON.sm} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" size="sm">
              小
            </Button>
            <Button variant="primary">中</Button>
            <Button variant="primary" size="lg">
              大
            </Button>
            <Button variant="primary" disabled>
              無効
            </Button>
          </div>
        </div>
      </Block>

      <Block title="メニュー・ポップオーバー（画面全体のテーマで表示）">
        <div className="flex flex-wrap items-center gap-2">
          <Menu>
            <MenuTrigger asChild>
              <Button>
                メニュー
                <Icon name="chevronDown" size={ICON.sm} />
              </Button>
            </MenuTrigger>
            <MenuContent align="start">
              <MenuLabel>taro@example.com</MenuLabel>
              <MenuItem icon="cog" shortcut="⌘,">
                設定
              </MenuItem>
              <MenuItem icon="folder" hint="中のフォルダ構成も再現します">
                フォルダを選ぶ
              </MenuItem>
              <MenuItem icon="pencil" disabled>
                名前を変更
              </MenuItem>
              <MenuSeparator />
              <MenuItem icon="trash" danger>
                ごみ箱へ移動
              </MenuItem>
            </MenuContent>
          </Menu>
          <Popover>
            <PopoverTrigger asChild>
              <Button>
                ポップオーバー
                <Icon name="chevronDown" size={ICON.sm} />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" title="モデル" className="w-[280px]">
              <div className="p-1.5">
                <PopoverOption selected label="Qwen3 8B" badge={<OptionBadge tone="accent">推奨</OptionBadge>} hint="GPU 機の会話モデル" />
                <PopoverOption label="DeepSeek" hint="外部 API" />
                <PopoverOption disabled label="GPT" badge={<OptionBadge>未設定</OptionBadge>} />
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </Block>

      <Block title="選択">
        <div className="flex flex-wrap items-center gap-4">
          <Segmented
            label="出典の表示"
            value={seg}
            options={[
              ["numbered", "番号"],
              ["chip", "チップ"],
              ["pill", "バッジ"],
            ]}
            onChange={setSeg}
          />
          <Switch label="見本" checked={on} onChange={setOn} />
          <Tabs defaultValue="a" className="w-full">
            <TabsList className="w-full">
              <TabsTrigger value="a">外観</TabsTrigger>
              <TabsTrigger value="b">回答</TabsTrigger>
              <TabsTrigger value="c">アカウント</TabsTrigger>
            </TabsList>
            <TabsContent value="a" />
          </Tabs>
        </div>
      </Block>

      <Block title="グループ化した一覧">
        <ListGroup title="ナレッジベース" footer="閲覧できるメンバーだけが検索結果に出ます。">
          <ListField label="公開範囲" hint="このナレッジベースを閲覧できる人">
            <Segmented
              label="公開範囲"
              value="team"
              options={[
                ["me", "自分のみ"],
                ["team", "チーム"],
              ]}
              onChange={() => {}}
            />
          </ListField>
          <ListField label="出典を必須にする" badge="require_citation" changed>
            <Switch label="出典を必須にする" checked onChange={() => {}} />
          </ListField>
          <ListItem>
            <span className="flex-1 text-body">メンバー</span>
            <span className="text-body text-muted">12 人</span>
            <Icon name="chevronRight" size={ICON.sm} className="text-muted-2" />
          </ListItem>
        </ListGroup>
      </Block>
    </section>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h2 className="m-0 text-footnote font-semibold text-muted">{title}</h2>
      {children}
    </div>
  );
}
