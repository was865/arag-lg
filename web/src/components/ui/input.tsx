/**
 * サーバー・クライアントのどちらからも使えるよう hook を使わない（"use client" を付けない）。
 *
 * 入力欄（1 行・選択・複数行・検索）と、その見出し。
 * 大きさは 4 段階: sm（表の行の中）/ md（ツールバー）/ lg（ダイアログのフォーム）/ xl（ログイン画面）。
 */
import { cva, type VariantProps } from "class-variance-authority";
import { Icon, type IconName } from "@/components/icons";
import { IconButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FRAME =
  "rounded-control border-[0.5px] border-divider-strong bg-surface text-fg outline-none transition-[border-color,box-shadow] placeholder:text-muted-2 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20 disabled:opacity-50";

export const inputVariants = cva(FRAME, {
  variants: {
    size: {
      sm: "h-7 px-2 text-footnote",
      md: "h-8 px-2.5 text-body",
      lg: "h-9 px-3 text-body",
      xl: "h-10 px-3 text-callout",
    },
  },
  defaultVariants: { size: "lg" },
});

type Size = VariantProps<typeof inputVariants>["size"];

/** 既存の呼び出し向け（lg・幅いっぱい） */
export const inputClass = cn(inputVariants({ size: "lg" }), "w-full");

export function Input({ size, className, ...props }: Omit<React.ComponentProps<"input">, "size"> & { size?: Size }) {
  return <input className={cn(inputVariants({ size }), "w-full", className)} {...props} />;
}

export function Select({ size, className, ...props }: Omit<React.ComponentProps<"select">, "size"> & { size?: Size }) {
  // OS の矢印は右端に詰まり、テーマにも合わないので、自前の矢印（select-chevron）を右に余白を取って置く
  return <select className={cn(inputVariants({ size }), "select-chevron cursor-pointer appearance-none pr-7", className)} {...props} />;
}

/** 複数行。高さは rows で決めるので、size からは文字と余白だけを使う */
export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea className={cn(FRAME, "w-full resize-none px-2.5 py-2 text-footnote", className)} {...props} />;
}

/**
 * 先頭にアイコンが付いた検索欄。placeholder を読み上げ名にも使う。
 * onClear を渡すと、入力があるときに消すボタンを出す。
 */
export function SearchField({
  size = "md",
  icon = "search",
  onClear,
  className,
  placeholder,
  ...props
}: Omit<React.ComponentProps<"input">, "size"> & {
  size?: "md" | "lg";
  icon?: IconName;
  onClear?: () => void;
}) {
  return (
    <label
      className={cn(
        FRAME,
        "flex items-center gap-2 px-2.5 text-muted focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20",
        size === "lg" ? "h-9" : "h-8",
        className,
      )}
    >
      <Icon name={icon} size={13} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        className="min-w-0 flex-1 border-0 bg-transparent text-body text-fg outline-none placeholder:text-muted-2"
        {...props}
      />
      {onClear && props.value ? (
        <IconButton size="icon-sm" label="検索語を消す" tooltip={false} icon="close" iconSize={12} onClick={onClear} />
      ) : null}
    </label>
  );
}

/** 見出し付きの入力欄（label で包むのでクリックで入力欄に移る） */
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    // content-start: 横に並べた隣の Field が高い（注記がある）ときも、行を伸ばさず入力欄の高さをそろえる
    <label className={cn("grid content-start gap-1.5", className)}>
      <span className="text-footnote font-medium text-fg-2">{label}</span>
      {children}
      {hint && <span className="text-caption text-muted">{hint}</span>}
    </label>
  );
}
