import { notFound } from "next/navigation";
import { Gallery } from "./gallery";

export const metadata = { title: "UI 部品 — ARag" };

/** UI 部品の一覧（開発用。本番ビルドでは出さない）。 */
export default function DevUiPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <Gallery />;
}
