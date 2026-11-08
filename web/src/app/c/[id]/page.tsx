import { Suspense } from "react";
import { ChatApp } from "@/components/chat/chat-app";

async function Thread({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChatApp initialRoute={{ view: "chat", threadId: id }} />;
}

// スレッド ID はリクエスト時に決まるので、殻（読み込み中）だけ先に返す
export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Thread params={params} />
    </Suspense>
  );
}
