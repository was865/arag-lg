import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { McpToolDetail } from "@/components/admin/mcp-tool-detail";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "ツールの審査 — ARag" };

type Params = Promise<{ server: string; tool: string }>;

/** owner・admin だけ（specs/038）。それ以外はチャットへ戻す。 */
async function Guarded({ params }: { params: Params }) {
  const { server, tool } = await params;
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fsystems%2Ftools");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <McpToolDetail serverName={decodeURIComponent(server)} toolName={decodeURIComponent(tool)} />;
}

export default function McpToolPage({ params }: { params: Params }) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded params={params} />
    </Suspense>
  );
}
