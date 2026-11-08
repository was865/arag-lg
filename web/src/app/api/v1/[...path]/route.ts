import { proxy, proxyOptionsFromEnv } from "@/lib/api/proxy";

// request を読むので cacheComponents の下でも常にリクエスト時に実行される

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(request: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  return proxy(request, path, proxyOptionsFromEnv());
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
