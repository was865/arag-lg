/** Better Auth の利用者 → 画面用の AppUser。 */
import type { AppUser } from "@/lib/types";

export interface SessionUserLike {
  name: string;
  email: string;
  emailVerified: boolean;
  createdAt?: Date | string;
  updatedAt?: Date | string;
}

const ORG = "ARag";

export function initialsOf(name: string, email: string): string {
  const n = name.trim();
  if (!n) return (email[0] ?? "?").toUpperCase();
  if (/^[\x20-\x7e]+$/.test(n)) {
    const words = n.split(/\s+/).filter(Boolean);
    return words
      .slice(0, 2)
      .map((w) => w[0]!.toUpperCase())
      .join("");
  }
  return [...n][0]!;
}

export function toAppUser(u: SessionUserLike): AppUser {
  const name = u.name.trim() || u.email.split("@")[0]!;
  const stamp = u.updatedAt ?? u.createdAt ?? new Date(0);
  return {
    name,
    firstName: name.split(/\s+/)[0] ?? name,
    org: ORG,
    initials: initialsOf(u.name, u.email),
    email: u.email,
    onboardedAt: null,
    emailVerifiedAt: u.emailVerified ? new Date(stamp).toISOString() : null,
  };
}

/** セッション一覧に出す端末名（ブラウザ · OS）。 */
export function describeAgent(ua: string | null | undefined): string {
  if (!ua) return "不明な端末";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Firefox\//.test(ua)
      ? "Firefox"
      : /Chrome\//.test(ua)
        ? "Chrome"
        : /Safari\//.test(ua)
          ? "Safari"
          : "ブラウザ";
  const os = /iPhone|iPad/.test(ua)
    ? "iOS"
    : /Android/.test(ua)
      ? "Android"
      : /Mac OS X|Macintosh/.test(ua)
        ? "macOS"
        : /Windows/.test(ua)
          ? "Windows"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return os ? `${browser} · ${os}` : browser;
}
