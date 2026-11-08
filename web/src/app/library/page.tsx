import { ChatApp } from "@/components/chat/chat-app";

export default function LibraryPage() {
  return <ChatApp initialRoute={{ view: "library", kbId: null }} />;
}
