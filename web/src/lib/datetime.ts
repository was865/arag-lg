/** 会話のタイムスタンプ表示用フォーマッタ。
 *  日付語（年月日）と時刻は zh/ja で共通のため、ロケール依存は呼び出し側の
 *  「今日／昨日」ラベルのみ。整形は ICU 差異を避けるため手組みで決定的に行う。 */

const pad2 = (n: number): string => (n < 10 ? `0${n}` : `${n}`);

/** 暦日の月日文字列。基準年と異なる場合のみ年を前置する（例: 6月5日 / 2025年6月5日）。 */
function ymd(d: Date, now: Date): string {
  const md = `${d.getMonth() + 1}月${d.getDate()}日`;
  return d.getFullYear() === now.getFullYear() ? md : `${d.getFullYear()}年${md}`;
}

/** ローカルタイム基準で同じ暦日か。 */
export function sameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** ホバー用の時刻表記「14:32」。日付はセパレータで示すため時刻のみ。不正値は空文字。 */
export function formatTurnTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** 日付セパレータ表記。今日/昨日は相対ラベル、それ以外は月日（別年なら年付き）。 */
export function dateSeparator(
  iso: string,
  now: Date,
  labels: { today: string; yesterday: string },
): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  if (sameLocalDay(d, now)) return labels.today;
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (sameLocalDay(d, yesterday)) return labels.yesterday;
  return ymd(d, now);
}

/** 社内システムの取得時刻「2026-11-18 20:19」（specs/032）。システムが返した時刻をそのまま見せ、時差で直さない。 */
export function formatFetchedAt(iso: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(iso);
  return m ? `${m[1]} ${m[2]}` : iso;
}

/** 時刻（UTC の ISO）を端末の時刻「2026-11-19 20:14」で。不正値は空文字。 */
export function formatLocalMinute(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
