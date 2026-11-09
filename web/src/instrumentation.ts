/** サーバ起動時の処理（Next の instrumentation）。認証表のマイグレーションを 1 回だけ流す。 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (process.env.ARAG_DEV_USER_ID) return; // 認証を使わない開発構成
  const { migrateAuth } = await import("@/lib/auth/migrate");
  try {
    await migrateAuth();
  } catch (e) {
    console.error("[auth] 認証表のマイグレーションに失敗しました", e);
  }
}
