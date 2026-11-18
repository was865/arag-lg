/**
 * 面（カード）。一覧のまとまり・根拠・設定の塊など、背景から一段浮いた四角はすべてこれで作る。
 * 角丸・縁・面の色は tone だけで決め、呼び出し側では並び・余白・幅だけを足す。
 * - surface: 既定の白い面（縁は divider-strong）
 * - sunken: 一段沈んだ面（補足・入力の下書き）
 * - raised: 浮いた面（影 e1。押せるカード）
 * - linked: 押せて、同じ鍵の印とホバーで互いに光るカード（回答の根拠カード。ui/link-marks と組む）
 * サーバーからも使えるよう hook を使わない。
 */
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// 面の組み合わせは globals.css の @utility card・card-sunken・card-raised（文字列の className でも同じものを使える）
export const cardClass = cva("", {
  variants: {
    tone: {
      surface: "card",
      sunken: "card-sunken",
      raised: "card-raised",
      linked:
        "card-raised outline-none transition-[transform,box-shadow,border-color] duration-(--duration-mid) ease-out hover:shadow-e2 focus-visible:ring-2 focus-visible:ring-accent/50 data-[on]:border-accent data-[on]:shadow-[0_0_0_3px_var(--accent-soft),var(--shadow-2)] motion-reduce:transition-none",
    },
  },
  defaultVariants: { tone: "surface" },
});

export function Card({
  tone,
  asChild,
  className,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof cardClass> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "div";
  return <Comp className={cn(cardClass({ tone }), className)} {...props} />;
}
