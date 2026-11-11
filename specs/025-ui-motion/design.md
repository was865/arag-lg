# 025 設計（第 1 段階）

## 動きの値（R1・R2・R10）

`web/src/lib/motion.ts` に置き、`globals.css` の `@theme` と同じ値にする。テストは `globals.css` を読んで一致を確かめる。

| 名前 | 値 | 用途 |
|---|---|---|
| `--duration-fast` | 120ms | ホバー・押下 |
| `--duration-mid` | 200ms | メニュー・ポップオーバー・カード |
| `--duration-slow` | 320ms | ダイアログ・画面の切り替え |
| `--ease-spring` | `cubic-bezier(0.3, 1.3, 0.5, 1)` | 出るとき（わずかに行き過ぎて戻る） |
| `--ease-out` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | 淡く現れるだけのとき |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | 消えるとき（出る時間の約 2/3） |

Tailwind v4 の `--ease-*` は `ease-spring` などのクラスになる。時間は `--animate-*` の中で使う。
Motion にはばね（`SPRING = { type: "spring", stiffness: 520, damping: 38, mass: 0.9 }`）を渡す。CSS の `--ease-spring` に見た目を合わせた値。

## 閉じるときの動き（R11）

Radix の Presence は、`data-state="closed"` になった要素の `animation-name` が変わると、そのアニメーションが終わるまで DOM に残す。
よって Motion は使わず CSS だけで足りる。

- メニュー・ポップオーバー: `data-[state=open]:animate-menu-in data-[state=closed]:animate-menu-out`。
  拡大の起点は Radix が出す `--radix-dropdown-menu-content-transform-origin` / `--radix-popover-content-transform-origin`。
- ダイアログ: 暗転は `overlay-in/out`、本体は広い画面で `dialog-in/out`（拡大 + 淡く）、狭い画面で `sheet-in/out`（下から）。
- `motion-reduce:` では `animate-none`（R5）。Presence はアニメーションが無ければすぐに外す。

## Motion の土台（R5・R7）

- `motion@14.7.1`（MIT、2026-10-27 公開。2 週間以上前の版）を固定版で入れる。
- `components/motion-provider.tsx`（"use client"）で `<MotionConfig reducedMotion="user" transition={SPRING}>` を全体に被せる。
- `motion/react` の `m` + `LazyMotion features={domAnimation}` で読み込みを小さくする（layout は `domMax` が要るので `domMax`）。

## セグメント（R12）

選択中の背景を別の要素にし、`<m.span layoutId={...}>` で移す。`layoutId` は `useId()` で部品ごとに分ける（同じ画面に 2 つあっても混ざらない）。
読み上げは今のまま `role="radio"` と `aria-checked`。

## トースト（R13）

- `AnimatePresence` で出入りを動かす。各トーストは `m.div` で、同じ格子のマス（`grid-area: 1 / 1`）に重ねて y と拡大だけを動かす。
- 束: 新しい順に i 番目を `y = -i*14px`、`scale = 1 - i*0.05`、`opacity = 1 - i*0.18`。i ≥ 3 は `opacity 0`（読み上げからも隠す: `aria-hidden`）。
- 束の上にポインタがある、または中にフォーカスがあるときは広げる: `y = -(高さ + 8) * i`、拡大 1、すべて表示。
- 位置の計算は純粋関数 `stackStyle(index, expanded)` に分けてテストする。
- 束の容器は `<section aria-label="通知">`（region として読み上げる）、各トーストの中身は今のまま。

## ボタンの押下（R14）

`buttonVariants` の基底に `active:scale-[0.97]`・`motion-reduce:active:scale-100` と、transition に transform を足す。`disabled` は既に pointer-events-none なので縮まない。
IconButton も同じ基底を使うので同時に効く。
