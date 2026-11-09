import "server-only";
import { log } from "@/lib/log";

/** 起動時に認証表を作る・足りない列を足す（specs/006-auth R19）。Python の Alembic とは独立。 */
import { getMigrations } from "better-auth/db/migration";
import { AUTH_SCHEMA, authOptions, authPool } from "@/lib/auth/server";

export async function migrateAuth(): Promise<void> {
  await authPool().query(`CREATE SCHEMA IF NOT EXISTS ${AUTH_SCHEMA}`);
  const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(authOptions());
  if (toBeCreated.length || toBeAdded.length) {
    await runMigrations();
    log("info", "auth.migrated", {
      created: toBeCreated.map((t) => t.table),
      altered: toBeAdded.map((t) => t.table),
    });
  }
}
