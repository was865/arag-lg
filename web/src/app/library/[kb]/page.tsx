import { Suspense } from "react";
import { ChatApp } from "@/components/chat/chat-app";

async function Library({ params }: { params: Promise<{ kb: string }> }) {
  const { kb } = await params;
  return <ChatApp initialRoute={{ view: "library", kbId: kb }} />;
}

// KB の ID はリクエスト時に決まるので、殻（読み込み中）だけ先に返す
export default function KbLibraryPage({
  params,
}: {
  params: Promise<{ kb: string }>;
}) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Library params={params} />
    </Suspense>
  );
}
