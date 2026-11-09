/** セッション → Python 用 JWT のキャッシュ（specs/006-auth R13）。
 * Better Auth の JWT は 15 分。毎回発行し直すと署名と DB 参照が増えるので、期限の 60 秒前まで使い回す。 */

const MARGIN_MS = 60_000;

/** JWT の exp（秒）。署名は検証しない（自分で発行したものを読むだけ）。 */
export function jwtExp(token: string): number | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const payload = JSON.parse(Buffer.from(part, "base64url").toString("utf8")) as { exp?: unknown };
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

interface Entry {
  token: string;
  expMs: number;
}

export class TokenCache {
  private entries = new Map<string, Entry>();
  private pending = new Map<string, Promise<string>>();
  private readonly now: () => number;
  private readonly max: number;

  constructor({ now = Date.now, max = 1000 }: { now?: () => number; max?: number } = {}) {
    this.now = now;
    this.max = max;
  }

  get size(): number {
    return this.entries.size;
  }

  async get(sessionId: string, mint: () => Promise<string>): Promise<string> {
    const hit = this.entries.get(sessionId);
    if (hit && hit.expMs - MARGIN_MS > this.now()) return hit.token;
    const inflight = this.pending.get(sessionId);
    if (inflight) return inflight;
    const p = mint()
      .then((token) => {
        const exp = jwtExp(token);
        if (exp !== null) {
          this.entries.delete(sessionId);
          this.entries.set(sessionId, { token, expMs: exp * 1000 });
          while (this.entries.size > this.max) {
            const oldest = this.entries.keys().next().value;
            if (oldest === undefined) break;
            this.entries.delete(oldest);
          }
        }
        return token;
      })
      .finally(() => this.pending.delete(sessionId));
    this.pending.set(sessionId, p);
    return p;
  }

  forget(sessionId: string): void {
    this.entries.delete(sessionId);
  }
}
