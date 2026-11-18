/**
 * 印（specs/025 R43）。ブランド印の「右上の引用の四角」を朱色の印にしたもので、根拠（引用）を示す。
 * 番号を入れると引用の印、番号なしは飾り（ブランド印の四角）。サーバーからも使えるよう hook を使わない。
 */
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const sealClass = cva(
  "inline-grid shrink-0 place-items-center rounded-[3px] bg-accent font-mono font-bold leading-none text-white nums",
  {
    variants: {
      size: {
        sm: "h-[15px] min-w-[15px] px-[3px] text-[9.5px]",
        md: "h-[18px] min-w-[18px] px-1 text-[11px]",
      },
    },
    defaultVariants: { size: "sm" },
  },
);

export function Seal({
  n,
  size,
  className,
  ...props
}: Omit<React.ComponentProps<"span">, "children"> & VariantProps<typeof sealClass> & { n?: number }) {
  return (
    <span aria-hidden={n === undefined ? true : undefined} className={cn(sealClass({ size }), className)} {...props}>
      {n}
    </span>
  );
}
