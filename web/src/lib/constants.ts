/** localStorage keys + cross-cutting constants. */
export const THEME_STORAGE_KEY = "arag.tweaks";
export const SESSION_STORAGE_KEY = "arag.session";
export const MODEL_STORAGE_KEY = "arag.model";
export const AGENT_CFG_STORAGE_KEY = "arag.agentCfg";
// オンボーディング記録の per-user localStorage キー（API 失敗時の再表示防止）。
// 旧キー "arag.onboarded"（グローバル）から user-scoped へ移行。
export const ONBOARDING_STORAGE_PREFIX = "arag:onboarded";

/** Auth cookie name used by the JWT routes + middleware.
 *  __Host- プレフィクスはブラウザに以下を強制させ、サブドメインからの上書き等を構造的に防ぐ:
 *    - Secure 属性必須（HTTPS / localhost のセキュアコンテキストでしか set/送信されない）
 *    - Path=/ 必須
 *    - Domain 属性禁止（明示すると set 自体が失敗する → サブドメイン共有不可）
 *  LAN over plain HTTP の dev で動かす場合は HTTPS（mkcert 等）の用意が必要。 */
export const AUTH_COOKIE = "__Host-arag_token";

/** User-selectable accent presets (sage / coral / cobalt / violet). */
export const ACCENT_PRESETS = ["#3FA77E", "#D97757", "#3D7EE6", "#8B6FE0"] as const;

export const DEFAULT_ACCENT = ACCENT_PRESETS[1];

/** standalone PWA のステータスバー背景（theme-color meta）に使うテーマ別背景色。
 *  globals.css の --bg（.theme-light / .theme-dark）と一致させること。 */
export const THEME_COLOR_LIGHT = "#faf8f3";
export const THEME_COLOR_DARK = "#16151a";

/** Accepted upload extensions (mirrors the composer file input).
 *  MinerU が解析できる docx/xlsx/pptx・PDF・画像と、テキストパーサで扱う
 *  md/txt/json/csv に加え、旧 Office(.doc/.xls/.ppt)・ODF(.odt/.ods/.odp)・.rtf を
 *  受理する。後者は rag 側 dispatch が soffice で docx/xlsx/pptx へ正規化してから索引化する
 *  （rag/app/documents_service.py の OFFICE_CONVERT_MAP と整合させること）。 */
export const ACCEPTED_FILE_TYPES =
  ".pdf,.docx,.doc,.xlsx,.xls,.csv,.pptx,.ppt,.odt,.ods,.odp,.rtf,.txt,.md,.json,.png,.jpg,.jpeg";
