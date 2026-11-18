/**
 * 小さなラベル（「閲覧のみ」「アーカイブ」「実行中」など）。状態を色だけでなく文字で示す。
 * サーバー・クライアントのどちらからも使えるよう hook を使わない。
 */
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-1.5 py-px text-mini font-semibold",
  {
    variants: {
      tone: {
        /** 既定の補足（閲覧のみ・件数など） */
        neutral: "bg-divider text-muted",
        /** 弱い状態（アーカイブ・未設定など） */
        outline: "border-[0.5px] border-divider-strong text-muted-2",
        /** 前向きな状態・推奨 */
        accent: "bg-accent-soft text-accent",
        /** 強調（目印として面の上に重ねるもの） */
        solid: "bg-accent-fill text-white",
        /** 失敗・取り消し */
        danger: "bg-danger-soft text-danger",
      },
      /** 等幅の大文字（実行中・取り消しなどの状態表示） */
      mono: { true: "font-mono uppercase tracking-[0.04em]", false: "" },
    },
    defaultVariants: { tone: "neutral", mono: false },
  },
);

export function Badge({
  tone,
  mono,
  className,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone, mono }), className)} {...props} />;
}
