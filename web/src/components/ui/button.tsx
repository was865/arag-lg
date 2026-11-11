/**
 * サーバー・クライアントのどちらからも使えるよう hook を使わない（"use client" を付けない）。
 *
 * ボタン（UI 試作）。見た目は variant と size だけで決め、呼び出し側で色や大きさを足さない。
 * - primary: 画面の主な操作（1 画面に 1 つ）
 * - secondary: それ以外の操作
 * - ghost: ツールバー・一覧の中の控えめな操作
 * - danger: 削除などの取り消せない操作
 * - danger-ghost: 一覧の中の削除など、目立たせすぎない赤い操作
 * - plain: 文字だけ（設定画面の「変更…」など）
 */
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Icon, type IconName } from "@/components/icons";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap font-medium transition-[background-color,filter,opacity,transform] duration-(--duration-fast) outline-none active:scale-[0.97] motion-reduce:active:scale-100 focus-visible:ring-2 focus-visible:ring-accent/50 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "bg-accent font-semibold text-white shadow-e1 hover:brightness-105 active:brightness-95",
        secondary: "border-[0.5px] border-divider-strong bg-surface text-fg shadow-e1 hover:bg-surface-2",
        ghost: "text-fg hover:bg-divider",
        danger: "bg-danger font-semibold text-white shadow-e1 hover:brightness-105 active:brightness-95",
        "danger-ghost": "text-danger hover:bg-danger-soft",
        plain: "h-auto px-0 text-accent hover:opacity-75",
      },
      size: {
        sm: "h-7 rounded-control px-2.5 text-footnote",
        md: "h-8 rounded-control px-3.5 text-body",
        lg: "h-10 rounded-control px-4 text-callout",
        icon: "h-7 w-7 rounded-control text-muted hover:text-fg",
        "icon-sm": "h-6 w-6 rounded-control text-muted hover:text-fg",
      },
    },
    compoundVariants: [{ variant: "plain", className: "h-auto px-0" }],
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

/** アイコンの大きさは 3 段階だけ（12 = 小さな印、14 = ボタン内、16 = 単独のアイコンボタン） */
export const ICON = { sm: 12, md: 14, lg: 16 } as const;

export function Button({
  className,
  variant,
  size,
  asChild,
  type = "button",
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

/**
 * アイコンだけのボタン。label は読み上げとツールチップの両方に使うので必須。
 * 既定は ghost（ツールバー・一覧の行の中）。
 */
export function IconButton({
  label,
  icon,
  iconSize = ICON.md,
  variant = "ghost",
  size = "icon",
  tooltip = true,
  children,
  ...props
}: Omit<React.ComponentProps<typeof Button>, "aria-label"> & {
  label: string;
  icon?: IconName;
  iconSize?: number;
  size?: "icon" | "icon-sm";
  /** false のときは title を付けない（隣に同じ文字がある場合など） */
  tooltip?: boolean;
}) {
  return (
    <Button aria-label={label} title={tooltip ? label : undefined} variant={variant} size={size} {...props}>
      {icon ? <Icon name={icon} size={iconSize} /> : children}
    </Button>
  );
}
