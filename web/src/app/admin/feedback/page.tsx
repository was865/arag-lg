import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { FeedbackView } from "@/components/admin/feedback-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "フィードバック — ARag" };

async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Ffeedback");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <FeedbackView />;
}

export default function FeedbackPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
