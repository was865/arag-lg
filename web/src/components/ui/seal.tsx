/**
 * 印（specs/025 R43）。ブランド印の「右上の引用の四角」を朱色の印にしたもので、根拠（引用）を示す。
 * 番号を入れると引用の印、番号なしは飾り（ブランド印の四角）。サーバーからも使えるよう hook を使わない。
 */
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const sealClass = cva(
  "inline-grid shrink-0 place-items-center rounded-[3px] font-mono font-bold leading-none nums",
  {
    variants: {
      /** accent は引用の印。neutral は引用ではない番号（解析の確認のチャンクなど）で、光ると朱になる */
      tone: {
        accent: "bg-accent text-white",
        neutral: "bg-fg/10 text-fg-2 data-[on]:bg-accent data-[on]:text-white",
      },
      size: {
        sm: "h-[15px] min-w-[15px] px-[3px] text-[9.5px]",
        md: "h-[18px] min-w-[18px] px-1 text-[11px]",
      },
    },
    defaultVariants: { size: "sm", tone: "accent" },
  },
);

export function Seal({
  n,
  size,
  tone,
  className,
  ...props
}: Omit<React.ComponentProps<"span">, "children"> & VariantProps<typeof sealClass> & { n?: number }) {
  return (
    <span aria-hidden={n === undefined ? true : undefined} className={cn(sealClass({ size, tone }), className)} {...props}>
      {n}
    </span>
  );
}
