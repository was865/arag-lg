/**
 * 回る輪（処理中の小さな印）。画面の読み込みには使わず骨組み（ui/skeleton）を使う。
 * ここは行の中の「解析中」「送信中」など、その場で続いている処理だけに使う。
 */
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const spinnerClass = cva("inline-block shrink-0 animate-spin-fast rounded-full motion-reduce:animate-none", {
  variants: {
    size: { xs: "h-[9px] w-[9px] border-[1.5px]", sm: "h-2.5 w-2.5 border-[1.5px]", md: "h-4 w-4 border-[1.5px]" },
    /** current は文字の色で回す（主ボタンなど色の付いた面の上。ダークでも面に合う） */
    tone: { default: "border-divider-strong border-t-accent", current: "border-current/30 border-t-current" },
  },
  defaultVariants: { size: "sm", tone: "default" },
});

export function Spinner({
  size,
  tone,
  label,
  className,
}: VariantProps<typeof spinnerClass> & {
  /** 読み上げる状態（「実行中」など）。隣に同じ文字があるなら付けない */
  label?: string;
  className?: string;
}) {
  return label ? (
    <span role="status" aria-label={label} className={cn(spinnerClass({ size, tone }), className)} />
  ) : (
    <span aria-hidden className={cn(spinnerClass({ size, tone }), className)} />
  );
}
