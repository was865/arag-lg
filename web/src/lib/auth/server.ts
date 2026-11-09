import "server-only";

/** Better Auth（specs/006-auth design §2）。認証表は Postgres の auth スキーマに置く。
 * 設定は環境変数から作るので、ビルド時に作られないよう getAuth() で遅延生成する。 */
import { betterAuth, type BetterAuthOptions } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { nextCookies } from "better-auth/next-js";
import { admin, jwt } from "better-auth/plugins";
import { adminAc, userAc } from "better-auth/plugins/admin/access";
import { Pool } from "pg";
import { inviteMail, isInviteUrl, resetPasswordMail, sendMail, verificationMail } from "@/lib/auth/mail";

export const AUTH_SCHEMA = "auth";
export const API_AUDIENCE = "arag-api";

export function authBaseUrl(): string {
  return (process.env.BETTER_AUTH_URL ?? "http://localhost:3100").replace(/\/$/, "");
}

let pool: Pool | undefined;
export function authPool(): Pool {
  pool ??= new Pool({
    connectionString: process.env.ARAG_AUTH_DATABASE_URL ?? "postgresql://arag:arag@localhost:5433/arag",
    options: `-c search_path=${AUTH_SCHEMA}`,
    max: 10,
  });
  return pool;
}

export function authOptions() {
  const baseURL = authBaseUrl();
  return {
    appName: "ARag",
    baseURL,
    secret: process.env.BETTER_AUTH_SECRET,
    trustedOrigins: [baseURL],
    database: authPool(),
    emailAndPassword: {
      enabled: true,
      minPasswordLength: 8,
      maxPasswordLength: 128,
      // 未確認でもログインはできる（質問とアップロードは API が止める。R6・R7）
      requireEmailVerification: false,
      revokeSessionsOnPasswordReset: true,
      resetPasswordTokenExpiresIn: 60 * 60,
      sendResetPassword: async ({ user, url }) => {
        await sendMail((isInviteUrl(url) ? inviteMail : resetPasswordMail)(user.email, user.name, url));
      },
    },
    emailVerification: {
      sendOnSignUp: true,
      autoSignInAfterVerification: true,
      expiresIn: 24 * 60 * 60,
      sendVerificationEmail: async ({ user, url }) => {
        await sendMail(verificationMail(user.email, user.name, url));
      },
    },
    session: {
      expiresIn: 30 * 24 * 60 * 60,
      updateAge: 24 * 60 * 60,
      // 中継のたびに DB を引かないよう、Cookie に 5 分だけ控えを持つ（失効の反映も最大 5 分遅れる）
      cookieCache: { enabled: true, maxAge: 5 * 60 },
    },
    rateLimit: {
      enabled: true,
      window: 60,
      max: 200,
      customRules: {
        "/sign-in/email": { window: 60, max: 5 },
        "/sign-up/email": { window: 60, max: 3 },
        "/request-password-reset": { window: 60, max: 3 },
        "/send-verification-email": { window: 60, max: 3 },
        "/change-password": { window: 60, max: 5 },
      },
    },
    hooks: {
      // 管理エンドポイントはブラウザから直接呼ばせない。/api/admin/members（権限の規則つき）が
      // サーバ内で auth.api.* として呼ぶ（request が無い）ものだけを通す（specs/010-admin-members R7）
      before: createAuthMiddleware(async (ctx) => {
        if (ctx.path.startsWith("/admin/") && ctx.request) {
          throw new APIError("FORBIDDEN", { message: "この操作はメンバー管理画面から行ってください" });
        }
      }),
    },
    databaseHooks: {
      user: {
        create: {
          // 最初の利用者を owner にする（R1）
          before: async (user) => {
            const { rows } = await authPool().query<{ n: string }>('SELECT count(*) AS n FROM "user"');
            return { data: { ...user, role: Number(rows[0]?.n ?? 0) === 0 ? "owner" : "member" } };
          },
        },
      },
    },
    plugins: [
      admin({
        defaultRole: "member",
        adminRoles: ["owner", "admin"],
        // owner・admin は管理操作ができ、member は一般利用者（Python 側の Role と同じ 3 種）
        roles: { owner: adminAc, admin: adminAc, member: userAc },
      }),
      jwt({
        jwt: {
          issuer: baseURL,
          audience: API_AUDIENCE,
          expirationTime: "15m",
          definePayload: ({ user }) => ({
            email: user.email,
            email_verified: user.emailVerified,
            role: user.role ?? "member",
            name: user.name,
          }),
        },
      }),
      nextCookies(),
    ],
  } satisfies BetterAuthOptions;
}

function create() {
  return betterAuth(authOptions());
}

let instance: ReturnType<typeof create> | undefined;
export function getAuth() {
  instance ??= create();
  return instance;
}
