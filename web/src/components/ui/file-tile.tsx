/**
 * 文書の形式の札（形式の色を淡く敷いた四角に、形式のアイコン）。ライブラリの行・文書の見出し・ごみ箱で使う。
 * サーバーからも使えるよう hook を使わない。
 */
import { Icon, type IconName } from "@/components/icons";
import { getFileMeta } from "@/lib/file-types";
import { cn } from "@/lib/utils";

/** 形式の色を淡く敷く style（中身を差し替える行のボタンなど、要素を変えられない所で使う） */
export function fileTileStyle(color: string): React.CSSProperties {
  return { color, background: `color-mix(in srgb, ${color} 12%, transparent)` };
}

export function FileTile({
  filename,
  icon,
  color,
  className,
}: {
  /** ファイル名から形式を決める。icon・color を渡せばそちらを使う（フォルダなど） */
  filename?: string;
  icon?: IconName;
  color?: string;
  className?: string;
}) {
  const meta = filename ? getFileMeta(filename) : null;
  const c = color ?? meta?.color;
  return (
    <span
      className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-control", !c && "bg-surface-2 text-muted", className)}
      style={c ? fileTileStyle(c) : undefined}
    >
      <Icon name={icon ?? meta?.iconName ?? "fileGeneric"} size={15} />
    </span>
  );
}
