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

/** 利用者が選べるアクセント（朱 / 藍 / 常磐）。既定は朱（specs/025 R40）。
 *  紙の地・墨の文字・紅の危険色に馴染むよう、朱と同じ明るさ・深さの和の色だけにする（R48）。 */
export const ACCENT_PRESETS = ["#D2402B", "#4A76AE", "#438067"] as const;

export const DEFAULT_ACCENT = ACCENT_PRESETS[0];

/** standalone PWA のステータスバー背景（theme-color meta）に使うテーマ別背景色。
 *  globals.css の --bg（.theme-light / .theme-dark）と一致させること。 */
export const THEME_COLOR_LIGHT = "#f5f4f1";
export const THEME_COLOR_DARK = "#111214";

/** Accepted upload extensions (mirrors the composer file input).
 *  MinerU が解析できる docx/xlsx/pptx・PDF・画像と、テキストパーサで扱う
 *  md/txt/json/csv に加え、旧 Office(.doc/.xls/.ppt)・ODF(.odt/.ods/.odp)・.rtf を
 *  受理する。後者は rag 側 dispatch が soffice で docx/xlsx/pptx へ正規化してから索引化する
 *  （rag/app/documents_service.py の OFFICE_CONVERT_MAP と整合させること）。 */
export const ACCEPTED_FILE_TYPES =
  ".pdf,.docx,.doc,.xlsx,.xls,.csv,.pptx,.ppt,.odt,.ods,.odp,.rtf,.txt,.md,.markdown,.html,.htm,.json,.png,.jpg,.jpeg";
