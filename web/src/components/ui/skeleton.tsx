/**
 * 読み込み中の骨組み（specs/025 R32）。回転する輪の代わりに、これから出る内容の形を淡く見せる。
 * 速く読み込めたときにちらつかないよう、少し遅れて現れる。サーバーからも使えるよう hook を使わない。
 */
import { cn } from "@/lib/utils";

/** 淡く明滅する棒 1 本 */
export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cn("block animate-soft-pulse rounded-[5px] bg-divider-strong/70 motion-reduce:animate-none", className)} />;
}

const WIDTHS = ["w-[46%]", "w-[62%]", "w-[38%]", "w-[54%]", "w-[70%]", "w-[42%]"];

/** 一覧の骨組み（アイコン + 2 行の文字 + 右端の補助列） */
export function ListSkeleton({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div role="status" aria-busy className={cn("animate-skeleton-in px-2 py-1", className)}>
      <span className="sr-only">読み込み中</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 border-b-[0.5px] border-divider py-3">
          <Skeleton className="h-8 w-8 shrink-0 rounded-control" />
          <div className="grid min-w-0 flex-1 gap-2">
            <Skeleton className={cn("h-3", WIDTHS[i % WIDTHS.length])} />
            <Skeleton className="h-2.5 w-[24%]" />
          </div>
          <Skeleton className="h-2.5 w-12 max-md:hidden" />
        </div>
      ))}
    </div>
  );
}

/** 会話の骨組み（右寄せの質問 1 つと、回答の数行） */
export function TranscriptSkeleton() {
  return (
    <div role="status" aria-busy className="mx-auto flex w-full max-w-[1020px] animate-skeleton-in flex-col gap-6 px-8 pt-7 max-md:px-3.5">
      <span className="sr-only">読み込み中</span>
      <Skeleton className="h-10 w-[38%] self-end rounded-[16px_16px_4px_16px]" />
      <div className="grid gap-3">
        <Skeleton className="h-3 w-[30%]" />
        <Skeleton className="h-3.5 w-[82%]" />
        <Skeleton className="h-3.5 w-[74%]" />
        <Skeleton className="h-3.5 w-[56%]" />
      </div>
    </div>
  );
}
