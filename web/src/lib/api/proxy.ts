import "server-only";

/** ブラウザ → Next → Python API の中継（specs/005-agent D2）。
 *
 * - SSE・原本の Range 応答はバッファせず body をそのまま流す。
 * - ブラウザの切断（request.signal）を上流へ伝え、SSE の読み出しを止める。
 * - P3 は開発用の利用者ヘッダを付ける。P4 で Better Auth のセッションから JWT に置き換える。
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
  devUserId?: string;
  devRole?: string;
  fetchImpl?: typeof fetch;
}

export function proxyOptionsFromEnv(): ProxyOptions {
  return {
    baseUrl: process.env.API_BASE_URL ?? "http://localhost:8100",
    devUserId: process.env.ARAG_DEV_USER_ID ?? "dev",
    devRole: process.env.ARAG_DEV_ROLE ?? "admin",
  };
}

export function upstreamUrl(baseUrl: string, path: string[], search: string): string {
  const safe = path.map((p) => encodeURIComponent(p)).join("/");
  return `${baseUrl.replace(/\/$/, "")}/v1/${safe}${search}`;
}

export async function proxy(request: Request, path: string[], opts: ProxyOptions): Promise<Response> {
  const url = upstreamUrl(opts.baseUrl, path, new URL(request.url).search);
  const headers = new Headers();
  for (const h of REQUEST_HEADERS) {
    const v = request.headers.get(h);
    if (v) headers.set(h, v);
  }
  if (opts.devUserId) headers.set("x-dev-user-id", opts.devUserId);
  if (opts.devRole) headers.set("x-dev-role", opts.devRole);

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
