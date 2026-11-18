"use client";

/** UI 部品の見本帳。ライトとダークを左右に並べ、段階（文字・角丸・アイコン）と部品を一度に確認する。 */
import { useState } from "react";
import { BrandTile, Icon } from "@/components/icons";
import { ConfirmModal } from "@/components/modals/confirm-modal";
import { SettingsModal } from "@/components/settings/settings-modal";
import { Button, ICON, IconButton } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Popover, PopoverContent, PopoverOption, PopoverTrigger } from "@/components/ui/popover";
import { ListField, ListGroup, ListItem } from "@/components/ui/list";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { FileTile } from "@/components/ui/file-tile";
import { linkHandlers, linkMarks } from "@/components/ui/link-marks";
import { Spinner } from "@/components/ui/spinner";
import { Seal } from "@/components/ui/seal";
import { Input, SearchField, Select, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/feedback/toast-provider";
import { DURATION } from "@/lib/motion";

const TYPE = [
  ["font-display text-hero font-bold", "挨拶 32", "こんにちは、検証さん。"],
  ["font-display text-display font-bold", "大見出し 22", "11,490 件"],
  ["text-title", "タイトル 19", "ナレッジベース"],
  ["text-headline", "見出し 15", "設定"],
  ["text-callout", "チャット本文 14", "MX-17 の保証期間は納品日から 12 か月です。"],
  ["text-body", "本文 13", "表示名・パスワード・ログイン中の端末"],
  ["text-footnote", "補助 12.5", "3 件の資料 · 2 分前に更新"],
  ["text-caption", "注記 11.5", "外観の設定はこの端末にだけ保存されます。"],
  ["text-mini", "ラベル 10.5", "閲覧のみ · アーカイブ"],
] as const;

const MOTION = [
  ["速い", DURATION.fast, "ホバー・押下"],
  ["中", DURATION.mid, "メニュー・カード"],
  ["遅い", DURATION.slow, "ダイアログ・画面の切り替え"],
  ["消える", DURATION.exit, "閉じるとき（出るより短く）"],
] as const;

const TOASTS = [
  ["3 件の文書を追加しました", "success"],
  ["x01-部品台帳.xlsx を処理しています", "info"],
  ["共有リンクをコピーしました", "success"],
  ["アップロードできませんでした", "error"],
] as const;

const COLORS = [
  ["bg-bg", "紙 bg"],
  ["bg-surface", "面 surface"],
  ["bg-bg-2", "沈み bg-2"],
  ["bg-fg", "墨 fg"],
  ["bg-muted", "灰 muted"],
  ["bg-accent", "朱 accent"],
  ["bg-danger", "紅 danger"],
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
  const [q, setQ] = useState("MX-17");
  const toast = useToast();
  const [n, setN] = useState(0);
  return (
    <section className={cn(theme, "flex flex-col gap-8 bg-bg-2 px-6 py-6 text-fg")}>
      <p className="eyebrow m-0">
        {theme === "theme-light" ? "ライト" : "ダーク"}
      </p>

      <Block title="文字の段階（9 段。上の 2 つは太く、字間を詰める）">
        <div className="flex flex-col gap-2.5">
          {TYPE.map(([cls, name, sample]) => (
            <div key={cls} className="flex items-baseline gap-4">
              <code className="w-24 shrink-0 font-mono text-caption text-muted">{name}</code>
              <span className={cn(cls, "min-w-0 truncate")}>{sample}</span>
            </div>
          ))}
        </div>
      </Block>

      <Block title="色・印・ロゴ（朱は引用の印・送信・注意だけに使う）">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {COLORS.map(([cls, name]) => (
              <div key={cls} className="flex flex-col items-center gap-1.5">
                <div className={cn(cls, "h-11 w-14 rounded-control border-[0.5px] border-divider-strong shadow-e1")} />
                <code className="font-mono text-mini text-muted">{name}</code>
              </div>
            ))}
          </div>
          <p className="m-0 max-w-[46ch] text-callout leading-[1.8] text-fg-2">
            9 月に PM-04 が保守で止まった時間は、合計 <strong className="font-semibold text-fg">135 分</strong>です
            <Seal n={1} className="mx-0.5 align-[2px]" />。いちばん長かったのは 9 月 19 日の軸受交換でした
            <Seal n={1} className="mx-0.5 align-[2px]" />
            <Seal n={2} className="align-[2px]" />。
          </p>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-2 text-headline font-semibold tracking-[-0.015em]">
              <BrandTile size={24} />
              ARag
            </span>
            <BrandTile size={44} />
            <Seal n={3} size="md" />
            <div className="flex items-center gap-2 card px-3 py-2 shadow-e2">
              <Seal n={1} />
              <span className="text-footnote font-semibold">x02-保守記録_2026-09.xlsx</span>
              <span className="text-caption text-muted">関連度 0.98</span>
            </div>
          </div>
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
            <Button variant="danger-ghost">ごみ箱へ</Button>
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
                <PopoverOption selected label="Qwen3 8B" badge={<Badge tone="accent">推奨</Badge>} hint="GPU 機の会話モデル" />
                <PopoverOption label="DeepSeek" hint="外部 API" />
                <PopoverOption disabled label="GPT" badge={<Badge tone="outline">未設定</Badge>} />
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </Block>

      <Block title="入力欄・ラベル">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input size="sm" placeholder="sm 28" className="w-28" />
            <Input size="md" placeholder="md 32" className="w-28" />
            <Input size="lg" placeholder="lg 36" className="w-28" />
            <Input size="xl" placeholder="xl 40" className="w-28" />
            <Select size="md" defaultValue="member">
              <option value="member">メンバー</option>
              <option value="admin">管理者</option>
            </Select>
          </div>
          <SearchField value={q} onChange={(e) => setQ(e.target.value)} onClear={() => setQ("")} placeholder="文書名で探す" />
          <Textarea rows={2} placeholder="補足（任意）" />
          <div className="flex flex-wrap items-center gap-2">
            <Badge>閲覧のみ</Badge>
            <Badge tone="outline">アーカイブ</Badge>
            <Badge tone="accent">推奨</Badge>
            <Badge tone="solid">新着</Badge>
            <Badge tone="danger" mono>
              取消
            </Badge>
            <Badge tone="accent" mono>
              実行中
            </Badge>
          </div>
        </div>
      </Block>

      <Block title="動き（時間 3 段 + 消える）">
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-[auto_auto_1fr] items-baseline gap-x-4 gap-y-1">
            {MOTION.map(([name, sec, use]) => (
              <div key={name} className="contents">
                <code className="font-mono text-caption text-muted">{name}</code>
                <code className="font-mono text-caption nums">{sec * 1000}ms</code>
                <span className="text-caption text-muted-2">{use}</span>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => {
                const [msg, kind] = TOASTS[n % TOASTS.length];
                toast(msg, kind, 6000);
                setN(n + 1);
              }}
            >
              通知を出す
            </Button>
            <span className="text-caption text-muted">何回か押すと束になる。束に乗せると広がる。</span>
          </div>
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

      <Block title="面・小見出し・処理中・形式の札（className に同じ組み合わせを書き写さない）">
        <div data-gallery className="grid gap-2.5">
          <div className="grid grid-cols-3 gap-2.5">
            <Card className="p-3 text-footnote text-fg-2">surface（既定）</Card>
            <Card tone="sunken" className="p-3 text-footnote text-fg-2">
              sunken（補足）
            </Card>
            <Card tone="raised" className="p-3 text-footnote text-fg-2">
              raised（押せる）
            </Card>
          </div>
          <Card
            tone="linked"
            tabIndex={0}
            data-gallery-link
            {...linkHandlers((from, on) => linkMarks(from, "[data-gallery]", "[data-gallery-link],[data-gallery-mark]", on))}
            className="p-3 text-footnote text-fg-2"
          >
            linked: ホバーすると同じ鍵の印{" "}
            <span data-gallery-mark className="rounded-[3px] px-1 data-[on]:bg-accent-soft data-[on]:text-accent">
              [1]
            </span>{" "}
            と一緒に光る（ui/link-marks）
          </Card>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <span className="eyebrow">eyebrow（区切りの小見出し）</span>
          <span className="flex items-center gap-1.5 text-caption text-muted">
            <Spinner size="xs" /> xs
          </span>
          <span className="flex items-center gap-1.5 text-caption text-muted">
            <Spinner /> sm
          </span>
          <span className="flex items-center gap-1.5 text-caption text-muted">
            <Spinner size="md" /> md
          </span>
          <Button variant="primary" size="sm">
            <Spinner size="md" tone="current" />
            送信中
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {["手順書.pdf", "台帳.xlsx", "報告.docx", "説明.pptx", "メモ.md", "不明.bin"].map((f) => (
            <FileTile key={f} filename={f} />
          ))}
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
