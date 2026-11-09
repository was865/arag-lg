/** サーバ側の構造化ログ（1 行 1 JSON。docs/handoff.md「日志」）。console.* は使わない。 */

type Level = "info" | "warn" | "error";

function errorFields(e: unknown): Record<string, unknown> {
  if (e instanceof Error) return { error: e.message, error_type: e.name };
  return e === undefined ? {} : { error: String(e) };
}

export function formatLog(level: Level, event: string, fields: Record<string, unknown> = {}, err?: unknown): string {
  return JSON.stringify({ ts: new Date().toISOString(), level, logger: "web", event, ...fields, ...errorFields(err) });
}

export function log(level: Level, event: string, fields?: Record<string, unknown>, err?: unknown): void {
  const line = formatLog(level, event, fields, err) + "\n";
  (level === "error" ? process.stderr : process.stdout).write(line);
}
