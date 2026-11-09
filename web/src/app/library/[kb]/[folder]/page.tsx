import { Suspense } from "react";
import { ChatApp } from "@/components/chat/chat-app";

async function Folder({ params }: { params: Promise<{ kb: string; folder: string }> }) {
  const { kb, folder } = await params;
  return <ChatApp initialRoute={{ view: "library", kbId: kb, folderId: folder }} />;
}

// KB・フォルダの ID はリクエスト時に決まるので、殻（読み込み中）だけ先に返す
export default function FolderPage({ params }: { params: Promise<{ kb: string; folder: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Folder params={params} />
    </Suspense>
  );
}
