/** 人の検索と名前の解決（specs/024）。共有リスト・部門で人を選び、user_id を名前で見せるため。
 * ログインしていれば誰でも使える（社内の名簿）。停止中の人は出さない。 */
import { getAuth, authPool } from "@/lib/auth/server";
import { apiError } from "@/lib/admin/server";
import { log } from "@/lib/log";

const SEARCH_LIMIT = 20;
const MAX_IDS = 500;

export interface Person {
  id: string;
  name: string;
  email: string;
}

export async function GET(request: Request): Promise<Response> {
  const session = await getAuth().api.getSession({ headers: request.headers });
  if (!session) return apiError(401, "unauthenticated", "ログインが必要です");
  const params = new URL(request.url).searchParams;
  const q = params.get("q")?.trim() ?? "";
  const ids = (params.get("ids") ?? "").split(",").map((x) => x.trim()).filter(Boolean).slice(0, MAX_IDS);
  const all = params.get("all") === "1";
  const active = `coalesce(banned, false) = false`;
  try {
    const pool = authPool();
    if (ids.length > 0) {
      // 停止中の人も名前は解決する（共有リストに残っている行を読めるように）
      const res = await pool.query<Person>(`SELECT id, name, email FROM "user" WHERE id = ANY($1)`, [ids]);
      return Response.json({ items: res.rows });
    }
    if (all) {
      // 「全員」を人数で見せるため、停止中でない人の id だけ
      const res = await pool.query<{ id: string }>(`SELECT id FROM "user" WHERE ${active}`);
      return Response.json({ ids: res.rows.map((r) => r.id) });
    }
    if (!q) return Response.json({ items: [] });
    const like = `%${q.replace(/[\\%_]/g, (c) => `\\${c}`)}%`;
    const res = await pool.query<Person>(
      `SELECT id, name, email FROM "user" WHERE ${active} AND (name ILIKE $1 OR email ILIKE $1)
       ORDER BY name LIMIT ${SEARCH_LIMIT}`,
      [like],
    );
    return Response.json({ items: res.rows });
  } catch (e) {
    log("error", "people.query_failed", {}, e);
    return apiError(500, "people_failed", "人の一覧を取得できませんでした");
  }
}
