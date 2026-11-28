import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { McpToolsView } from "@/components/admin/mcp-tools-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "社内システムのツール — ARag" };

/** owner・admin だけ（specs/038）。それ以外はチャットへ戻す。 */
async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fsystems%2Ftools");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <McpToolsView />;
}

export default function McpToolsPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
