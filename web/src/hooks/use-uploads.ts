import type { UploadStatus } from "@/lib/types";

/** 添付の状態ごとに、× ボタンが何をするか（旧版 use-uploads から移植）。 */
export function uploadActionFor(status: UploadStatus): "abort" | "cancel" | "none" | "remove" {
  if (status === "uploading") return "abort";
  if (status === "queued") return "cancel";
  if (status === "processing") return "none";
  return "remove";
}
