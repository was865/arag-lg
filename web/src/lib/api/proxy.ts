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
  fetchImpl?: typeof fetch;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function upstreamUrl(baseUrl: string, path: string[], search: string): string {
  const safe = path.map((p) => encodeURIComponent(p)).join("/");
  return `${baseUrl.replace(/\/$/, "")}/v1/${safe}${search}`;
}

export async function proxy(request: Request, path: string[], opts: ProxyOptions): Promise<Response> {
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
      { error: { code: "upstream_unavailable", message: "サーバに接続できません。しばらくしてからお試しください" } },
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
