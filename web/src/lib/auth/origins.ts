/** 自サイトとして受け付ける Origin（specs/006-auth R14・R20）。
 * 正の URL は BETTER_AUTH_URL（JWT の iss・メールのリンクもこれ）。
 * ARAG_EXTRA_ORIGINS（カンマ区切り）で、Tailscale など別の入口からのログイン・送信も許す。 */
export function siteOrigins(baseUrl: string, extra: string | undefined): string[] {
  const out: string[] = [];
  for (const raw of [baseUrl, ...(extra ?? "").split(",")]) {
    const s = raw.trim();
    if (!s) continue;
    let origin: string;
    try {
      const u = new URL(s);
      if (u.protocol !== "http:" && u.protocol !== "https:") continue;
      origin = u.origin;
    } catch {
      continue;
    }
    if (!out.includes(origin)) out.push(origin);
  }
  return out;
}
