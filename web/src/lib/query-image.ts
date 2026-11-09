/** 質問に添える画像（specs/017-query-image R1）。送る前にブラウザで縮めて JPEG にする。 */

export const QUERY_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"] as const;
export const QUERY_IMAGE_ACCEPT = QUERY_IMAGE_TYPES.join(",");
/** 縮める前の元ファイルの上限（縮めた後は数百 KB になる）。 */
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_PX = 1600;

export interface QueryImage {
  /** data URL（JPEG）。送信にも縮小表示にも使う。 */
  dataUrl: string;
  width: number;
  height: number;
}

export function fitWithin(width: number, height: number, max: number): { width: number; height: number } {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** 添えられない理由（日本語）。問題なければ null。 */
export function checkImageFile(f: File): string | null {
  if (!(QUERY_IMAGE_TYPES as readonly string[]).includes(f.type)) return "画像は JPEG・PNG・WebP・GIF のいずれかにしてください";
  if (f.size > MAX_FILE_BYTES) return "画像が大きすぎます（20MB まで）";
  return null;
}

export function imageFromClipboard(dt: DataTransfer | null): File | null {
  if (!dt) return null;
  return Array.from(dt.files).find((f) => f.type.startsWith("image/")) ?? null;
}

/** 長辺 1600px 以内の JPEG にする（透明部分は白、GIF は最初のフレーム）。 */
export async function shrinkImage(f: File, maxPx = MAX_PX): Promise<QueryImage> {
  const bitmap = await createImageBitmap(f);
  try {
    const { width, height } = fitWithin(bitmap.width, bitmap.height, maxPx);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("画像を処理できませんでした");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(bitmap, 0, 0, width, height);
    return { dataUrl: canvas.toDataURL("image/jpeg", 0.85), width, height };
  } finally {
    bitmap.close();
  }
}

/** 表示中の画像（保存済みの URL・data URL）をもう一度送れる形にする（再生成・質問の編集）。 */
export async function imageFromUrl(url: string): Promise<QueryImage> {
  const res = await fetch(url);
  if (!res.ok) throw new Error("画像を取得できませんでした");
  const blob = await res.blob();
  return shrinkImage(new File([blob], "image", { type: blob.type || "image/jpeg" }));
}
