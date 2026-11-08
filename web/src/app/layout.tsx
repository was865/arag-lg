import type { Metadata } from "next";
import "./globals.css";

// フォント（Inter + Noto Sans JP）と旧版のデザイントークンは P4 の UI 移植で入れる。
export const metadata: Metadata = {
  title: "ARag",
  description: "社内文書に根拠を持って答えるナレッジアシスタント",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ja" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
