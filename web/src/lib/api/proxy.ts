import "server-only";

/** ブラウザ → Next → Python API の中継（specs/005-agent D2）。
 *
 * - SSE・原本の Range 応答はバッファせず body をそのまま流す。
 * - ブラウザの切断（request.signal）を上流へ伝え、SSE の読み出しを止める。
 * - 利用者は authorize（Better Auth のセッション → JWT、specs/006-auth R13）で渡す。
 *   開発・評価用に ARAG_DEV_USER_ID を明示したときだけ、代わりに利用者ヘッダを付ける（R17）。
 * - 状態を変える要求は Origin を確かめる（CSRF、R14）。
 */

const REQUEST_HEADERS = ["content-type", "accept", "last-event-id", "range", "if-none-match"];
const RESPONSE_HEADERS = [
  "content-type",
  "content-length",
  "content-disposition",
  "content-range",
  "accept-ranges",
  "cache-control",
  "etag",
  "x-accel-buffering",
  "x-request-id",
  "location",
];

export interface ProxyOptions {
  baseUrl: string;
  /** 上流へ付ける認証の見出し。応答を返したら上流を呼ばずにそれを返す（未ログインなど）。 */
  authorize?: (request: Request) => Promise<Headers | Response>;
  devUserId?: string;
  devRole?: string;
  /** GET・HEAD 以外で受け付ける Origin。未指定なら検査しない。 */
  allowedOrigins?: string[];
  /** API と共有する合言葉。あれば利用者の IP を見出しで伝える（監査ログ用）。 */
  forwardSecret?: string;
  fetchImpl?: typeof fetch;
}

/** 利用者の IP（Next が付ける X-Forwarded-For の先頭、無ければ X-Real-IP）。 */
export function clientIp(h: Headers): string | null {
  const first = h.get("x-forwarded-for")?.split(",")[0]?.trim();
  return first || h.get("x-real-ip")?.trim() || null;
}

/** API に利用者の IP を伝える見出し。API は合言葉が合うときだけ信じる。 */
export function forwardHeaders(h: Headers, secret: string | undefined): Record<string, string> {
  const ip = clientIp(h);
  if (!secret || !ip) return {};
  return { "x-arag-client-ip": ip, "x-arag-forward-token": secret };
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function upstreamUrl(baseUrl: string, path: string[], search: string): string {
  const safe = path.map((p) => encodeURIComponent(p)).join("/");
  return `${baseUrl.replace(/\/$/, "")}/v1/${safe}${search}`;
}

/** ブラウザから書かせない API（監査ログはサーバ間でだけ書く。specs/011-audit-log R4）。 */
function isServerOnlyWrite(method: string, path: string[]): boolean {
  const p = path.filter(Boolean).map((x) => x.toLowerCase());
  return !SAFE_METHODS.has(method) && p[0] === "admin" && p[1] === "audit";
}

export async function proxy(request: Request, path: string[], opts: ProxyOptions): Promise<Response> {
  if (isServerOnlyWrite(request.method, path)) {
    return Response.json({ error: { code: "forbidden", message: "この操作はできません" } }, { status: 403 });
  }
  const origin = request.headers.get("origin");
  if (!SAFE_METHODS.has(request.method) && origin && opts.allowedOrigins && !opts.allowedOrigins.includes(origin)) {
    return Response.json({ error: { code: "forbidden_origin", message: "許可されていない送信元です" } }, { status: 403 });
  }
  const url = upstreamUrl(opts.baseUrl, path, new URL(request.url).search);
  const headers = new Headers();
  for (const h of REQUEST_HEADERS) {
    const v = request.headers.get(h);
    if (v) headers.set(h, v);
  }
  if (opts.authorize) {
    const auth = await opts.authorize(request);
    if (auth instanceof Response) return auth;
    auth.forEach((v, k) => headers.set(k, v));
  } else if (opts.devUserId) {
    headers.set("x-dev-user-id", opts.devUserId);
    if (opts.devRole) headers.set("x-dev-role", opts.devRole);
  }
  for (const [k, v] of Object.entries(forwardHeaders(request.headers, opts.forwardSecret))) headers.set(k, v);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    signal: request.signal,
    cache: "no-store",
    redirect: "manual",
  };
  if (hasBody) init.duplex = "half";

  let upstream: Response;
  try {
    upstream = await (opts.fetchImpl ?? fetch)(url, init);
  } catch {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return Response.json(
      { error: { code: "upstream_unavailable", message: "サーバーに接続できません。しばらくしてからお試しください" } },
      { status: 502 },
    );
  }
  const out = new Headers();
  for (const h of RESPONSE_HEADERS) {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: out });
}
