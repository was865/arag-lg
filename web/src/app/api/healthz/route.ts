import { connection } from "next/server";

/** Web の liveness。ビルド時に静的化されないよう、リクエスト時に評価させる。 */
export async function GET() {
  await connection();
  return Response.json({ status: "ok" });
}
