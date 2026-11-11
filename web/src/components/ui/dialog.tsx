"use client";

/**
 * ダイアログ（UI 試作）。Radix Dialog の上に、アプリ共通の見た目（暗転・角丸・狭い画面ではシート）を載せる。
 * フォーカスの閉じ込め・Esc・背景のスクロール止め・閉じたあとのフォーカス復帰は Radix が受け持つ。
 */
import * as D from "@radix-ui/react-dialog";
import { Icon } from "@/components/icons";
import { Button, ICON } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogClose = D.Close;

const WIDTH = {
  sm: "w-[400px]",
  md: "w-[520px]",
  lg: "w-[600px]",
  xl: "w-[760px]",
  /** 表・文書を広く見るシート（ほぼ全画面） */
  full: "h-full max-h-full w-full max-w-[1100px] max-md:max-h-full max-md:rounded-none",
} as const;

export function DialogContent({
  title,
  description,
  size = "md",
  alert,
  layer = "base",
  hideClose,
  className,
  children,
  ...props
}: Omit<React.ComponentProps<typeof D.Content>, "title"> & {
  title: React.ReactNode;
  description?: React.ReactNode;
  size?: keyof typeof WIDTH;
  /** 確認ダイアログ（role="alertdialog"、閉じるボタンなし） */
  alert?: boolean;
  /** 他のダイアログの上に重ねるときは "top" */
  layer?: "base" | "top";
  hideClose?: boolean;
}) {
  return (
    <D.Portal>
      <D.Overlay
        className={cn(
          "fixed inset-0 grid place-items-center data-[state=open]:animate-overlay-in data-[state=closed]:animate-overlay-out bg-[rgba(20,18,15,0.35)] p-6 motion-reduce:animate-none! max-md:items-end max-md:p-0",
          layer === "top" ? "z-[250]" : "z-[230]",
          size === "full" && "p-4 max-md:p-0",
        )}
      >
        <D.Content
          role={alert ? "alertdialog" : "dialog"}
          className={cn(
            "flex max-h-[86vh] max-w-full flex-col overflow-hidden rounded-sheet border-[0.5px] border-divider-strong bg-surface shadow-e3 outline-none motion-reduce:animate-none!",
            // 広い画面は拡大しながら、狭い画面（シート）は下から出入りする（specs/025 R11）
            "data-[state=open]:animate-dialog-in data-[state=closed]:animate-dialog-out max-md:data-[state=open]:animate-sheet-in max-md:data-[state=closed]:animate-sheet-out",
            "max-md:max-h-[90dvh] max-md:w-full max-md:rounded-b-none",
            WIDTH[size],
            className,
          )}
          {...props}
        >
          <header className={cn("flex items-start gap-3 px-5 pt-4", alert ? "pb-1" : "pb-3")}>
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <D.Title className="m-0 text-headline font-semibold tracking-[-0.01em] text-fg">{title}</D.Title>
              {description ? (
                <D.Description className="m-0 whitespace-pre-line text-body text-muted">{description}</D.Description>
              ) : (
                <D.Description className="sr-only">{title}</D.Description>
              )}
            </div>
            {!alert && !hideClose && (
              <D.Close asChild>
                <Button variant="ghost" size="icon" aria-label="閉じる" className="-mr-1.5 -mt-0.5">
                  <Icon name="close" size={ICON.sm} />
                </Button>
              </D.Close>
            )}
          </header>
          {children}
        </D.Content>
      </D.Overlay>
    </D.Portal>
  );
}

/**
 * 見出しなどを自前で組む大きなダイアログ用（ヘルプなど）。暗転・フォーカス・Esc だけを受け持つ。
 * title は読み上げ用（画面には出さない）。
 */
export function DialogFrame({
  title,
  layer = "base",
  className,
  children,
  ...props
}: Omit<React.ComponentProps<typeof D.Content>, "title"> & { title: string; layer?: "base" | "top" }) {
  return (
    <D.Portal>
      <D.Overlay
        className={cn(
          "fixed inset-0 grid place-items-center data-[state=open]:animate-overlay-in data-[state=closed]:animate-overlay-out bg-[rgba(20,18,15,0.35)] p-6 motion-reduce:animate-none! max-md:p-0",
          layer === "top" ? "z-[250]" : "z-[230]",
        )}
      >
        <D.Content
          aria-describedby={undefined}
          className={cn(
            "max-w-full overflow-hidden rounded-sheet border-[0.5px] border-divider-strong bg-surface shadow-e3 outline-none data-[state=open]:animate-dialog-in data-[state=closed]:animate-dialog-out motion-reduce:animate-none!",
            className,
          )}
          {...props}
        >
          <D.Title className="sr-only">{title}</D.Title>
          {children}
        </D.Content>
      </D.Overlay>
    </D.Portal>
  );
}

/** ダイアログの本文（スクロールする部分） */
export function DialogBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("min-h-0 flex-1 overflow-y-auto px-5 pb-[max(20px,env(safe-area-inset-bottom))]", className)}
      {...props}
    />
  );
}

/** ダイアログ下端のボタン列（右寄せ。狭い画面では横いっぱいに並べる） */
export function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex justify-end gap-2 px-5 pb-[max(16px,env(safe-area-inset-bottom))] pt-4 max-md:[&>*]:flex-1",
        className,
      )}
      {...props}
    />
  );
}
