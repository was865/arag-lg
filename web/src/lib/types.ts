/** Shared domain types for the ARag agentic-RAG workspace. */

import type { IconName } from "@/components/icons";
import type { TurnFeedback } from "@/lib/feedback-types";

// ── Sources / citations ─────────────────────────────────────────────────────
export type SourceType = "meeting" | "wiki" | "slack" | "doc";

export interface SourceSection {
  id: string;
  heading: string;
  body: string;
  highlight?: boolean;
  blockType?: string;
  page?: number;
}

export interface Source {
  id: string;
  type: SourceType;
  title: string;
  path: string;
  author: string;
  date: string;
  sections: SourceSection[];
  /** 文書内チャンクの再ランクスコア(0–1)の最大値。未取得なら undefined。 */
  score?: number;
}

/** Maps a citation number ([1], [2]…) to the source + section it opens. */
export type CitationMap = Record<number, { sourceId: string; sectionId: string }>;

// ── Agent tool calls ────────────────────────────────────────────────────────
export type ToolStatus = "pending" | "running" | "done" | "error";

export type ToolName =
  | "skill"
  | "read_image"
  | "switch_model"
  | "reasoning"
  | "rewrite_query"
  | "retrieve"
  | "embed"
  | "vector_search"
  | "bm25_search"
  | "rerank"
  | "expand"
  | "grade"
  | "verify"
  | "revise"
  | "review"
  | "system"
  | "understand"
  | "table_query"
  | "fetch_document"
  | "calculate"
  | "summarize"
  | "answer"
  | "web_search"
  | "python_sandbox"
  | "sql_query"
  | "work_calendar";

export interface RerankHit {
  id: string;
  score: number;
  title: string;
}

export interface ToolCall {
  id: string;
  name: ToolName;
  parentId?: string;
  label: string;
  status: ToolStatus;
  durationMs: number;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  summary: string;
  /** このステップを出した回答の流れの節点（specs/029。古い記録には無い） */
  node?: string;
}

// ── Threads ─────────────────────────────────────────────────────────────────
export type ThreadVisibility = "private" | "org" | "public";

export interface ThreadSummary {
  id: string;
  title: string;
  updated: string;
  pinned?: boolean;
  active?: boolean;
  /** 回答を生成中（別のスレッドを見ている間も裏で続く）。 */
  running?: boolean;
}

export interface CompletedThread {
  query: string;
  answerText: string;
  tokens: number;
  durationMs: number;
  /** メッセージ作成時刻（ISO 文字列）。表示の時刻・日付セパレータに使う。 */
  createdAt?: string;
  /** 永続メッセージ ID（フィードバック送信に使う。履歴復元で埋まる）。 */
  messageId?: string;
  /** 回答不能時の理由。null/未定義 = 回答できた。 */
  noAnswerReason?: string | null;
  /** 永続フィードバック（未評価は null）。共有閲覧では常に null。 */
  feedback?: TurnFeedback | null;
}

/** 1ターン分（ユーザー質問 + エージェント実行 + 回答）。 */
/** 質問に添えた画像（specs/017）。url は data URL（送信直後）か API の画像 URL（保存済み）。 */
export interface TurnImage {
  url: string;
  width?: number;
  height?: number;
  description?: string | null;
}

export interface Turn {
  query: string;
  /** 生成中だけ持つ、サーバが送ったままの回答と出典番号（answer・citationMap は出た順に振り直した表示用）。 */
  rawAnswer?: string;
  rawCitationMap?: CitationMap;
  /** 確認で差し戻された下書き。書き直した回答が届き始めるまで、薄く残して見せる（急に消さない）。 */
  staleAnswer?: string;
  image?: TurnImage;
  steps: ToolCall[];
  answer: string;
  streaming: boolean;
  citationMap: CitationMap;
  sourceIds: string[];
  sources: Source[];
  tokens: number;
  durationMs: number;
  status: "running" | "done" | "cancelled" | "error";
  attachments: string[];
  /** 添付の documentId（添付ありターンの retrieve スコープ・再生成再利用に使う。in-memory のみ）。 */
  attachmentDocIds?: string[];
  /** ターン作成時刻（ISO 文字列）。履歴は DB 値、ライブは送信時刻。表示用。 */
  createdAt?: string;
  /** 永続メッセージ ID（フィードバック送信に使う。ライブは saved イベント、履歴は API 由来）。 */
  messageId?: string;
  /** 永続フィードバック（未評価は null/undefined）。 */
  feedback?: TurnFeedback | null;
  /** 生成中・直近の run（再接続・取消に使う）。 */
  runId?: string;
  /** 回答に使ったモデルの id。 */
  modelId?: string;
  /** 回答不能の理由（null/未定義 = 回答できた）。 */
  noAnswerReason?: string | null;
  /** 続けて聞く質問の候補（specs/028）。最後のターンの下にだけ出す。 */
  suggestions?: string[];
  /** 報告の送信が 404 だった（メッセージが保存されていない）。「問題を報告」を以後出さない（specs/028 R12a） */
  unsaved?: boolean;
  /** 失敗したときの説明（日本語）。 */
  error?: string;
}

// ── Models / prompts / scope ────────────────────────────────────────────────
export interface ModelOption {
  id: string;
  label: string;
  tag: string;
  desc: string;
  /** 回答生成に使えるか（API キー設定済み）。未判定（undefined）は選択可として扱う。 */
  available?: boolean;
}

export interface SuggestedPrompt {
  icon: IconName;
  label: string;
  tag: string;
}

/** 空状態の「使い方ヒント」。クリックで composer に fill を流し込む（送信はしない）。 */
export interface UsageTip {
  icon: IconName;
  title: string;
  body: string;
  fill: string;
}

export interface ScopePreset {
  id: string;
  label: string;
  iconName: IconName;
  desc: string;
  sources: string[];
}

export interface ScopeValue {
  id: string;
  label: string;
  iconName: IconName;
  desc?: string;
  sources: string[];
  /** 実検索範囲: 特定 KB の id。null/undefined = アクセス可能な全 KB（既定）。
   * これが retrieve の kb_ids に反映される唯一のフィールド（presets/sources は装飾）。 */
  kbId?: string | null;
  /** 既定 undefined=false。true のとき archived KB も retrieve の include_archived に反映される。 */
  includeArchived?: boolean;
  /** 特定の文書だけに絞る（文書ビューアの「この文書に質問」）。retrieve の document_ids に反映される。 */
  documentIds?: string[];
}

export interface SourceConnector {
  id: string;
  label: string;
  iconName: IconName;
  count: string;
  color: string;
  darkColor?: string;
}

// ── User / auth ─────────────────────────────────────────────────────────────
export interface AppUser {
  name: string;
  firstName: string;
  org: string;
  initials: string;
  email: string;
  /** オンボーディングツアー完了時刻（ISO 文字列）。null なら初回ツアー未実施。 */
  onboardedAt: string | null;
  /** メール検証完了時刻（ISO 文字列）。null なら未検証。 */
  emailVerifiedAt: string | null;
}

// ── Uploads ─────────────────────────────────────────────────────────────────
export type UploadStatus = "uploading" | "queued" | "processing" | "ready" | "error" | "skipped";

// rag worker の段階キー（parsing→chunking→embedding→indexing→ready）。
// SSE 進捗で受け取り、段階ステッパーの現在位置に使う。
export type IngestStage = "parsing" | "chunking" | "embedding" | "indexing" | "ready";

export interface StagedFile {
  id: string;
  name: string;
  size: number;
  status: UploadStatus;
  progress: number;
  pages?: number | null;
  chunks?: number;
  error?: string;
  jobId?: string;
  /** アップロード応答で確定する rag 側 documentId（添付スコープ検索に使う）。 */
  documentId?: string;
  /** rag の現在段階キー（SSE 由来）。ステッパー表示に使う。 */
  stage?: IngestStage;
  /** 段階の日本語ラベル（例: 「埋め込み生成」）。SSE の stage_detail。 */
  stageDetail?: string;
  /** フォルダアップロード時の相対パス（キューのグループ表示用、UIのみ）。 */
  relPath?: string;
  /** 処理開始時刻（epoch ms）。所要時間の算出に使う。 */
  startedAt?: number;
  /** 索引化完了までの所要時間（ms）。ready 到達時に確定。 */
  durationMs?: number;
}

// ── Documents (管理) ────────────────────────────────────────────────────────
export interface DocumentSummary {
  id: string;
  filename: string;
  mime: string;
  size: number;
  page_count: number | null;
  status: string;
  created_at: string;
  chunk_count: number;
  latest_job_id: string | null;
  error: string | null;
  /** この文書の所属 KB に書込（=削除）できるか。所有者ではなく KB の write 権限で決まる。
   *  false の文書は削除 UI を抑止する（read-only KB / 権限なし）。 */
  can_write?: boolean;
  /** 共有元 KB 名（共有 KB の文書のみ）。出典バッジ表示に使う。 */
  kb_name?: string | null;
  /** 所属フォルダ（null/未定義 = KB ルート直下）。整理用の表示レイヤで検索には影響しない。 */
  folder_id?: string | null;
}

export interface DocumentListResponse {
  items: DocumentSummary[];
  next_cursor: string | null;
  total: number;
}

// ── Folders ─────────────────────────────────────────────────────────────────
/** KB 内の整理用フォルダ（自己参照ツリー）。rag が snake_case で返すためそのまま扱う。
 *  parent_id null = KB ルート直下。権限は KB から継承し、検索スコープには影響しない。 */
export interface FolderNode {
  id: string;
  kb_id: string;
  parent_id: string | null;
  name: string;
}

export interface FolderTreeResponse {
  items: FolderNode[];
}

export interface DocumentPreviewChunk {
  chunk_id: string;
  ordinal: number;
  heading_path: string;
  page_start: number;
  page_end: number;
  block_type: string;
  text: string;
}

export interface DocumentPreview {
  document_id: string;
  document_title: string;
  chunks: DocumentPreviewChunk[];
}

// ── Trash ───────────────────────────────────────────────────────────────────
/** ごみ箱の文書エントリ。GET /api/trash が返す items の要素。
 *  フィールド名は rag が snake_case で返し、route がそのまま透過するため snake_case のまま扱う。
 *  （DocumentSummary も page_count/created_at/chunk_count/kb_name を snake_case で保持する規約と揃える。） */
export interface TrashItem {
  id: string;
  filename: string;
  kb_id: string;
  /** personal KB のときは null。 */
  kb_name: string | null;
  mime: string;
  size: number;
  deleted_at: string;
  deleted_by: string;
  expires_at: string;
}

export interface TrashListResponse {
  items: TrashItem[];
}

export interface OrgTrashItem {
  id: string;
  filename: string;
  kb_id: string;
  kb_name: string | null;
  kb_kind: string;
  owner_user_id: string;
  /** personal KB のとき所有者メール（解決失敗時は owner_user_id）。共有 KB は null。 */
  owner_email: string | null;
  mime: string;
  size: number;
  deleted_at: string;
  deleted_by: string;
  expires_at: string;
}

export interface OrgTrashListResponse {
  items: OrgTrashItem[];
}

// ── Toasts ──────────────────────────────────────────────────────────────────
export type ToastKind = "info" | "success" | "error";
export interface Toast {
  id: string;
  msg: string;
  kind: ToastKind;
}

// ── Tweaks (persisted display preferences) ──────────────────────────────────
export type ToolView = "card" | "timeline" | "log";
export type Density = "compact" | "comfy";
export type CitationStyle = "numbered" | "chip" | "pill";

export interface Tweaks {
  dark: boolean;
  accent: string;
  toolView: ToolView;
  density: Density;
  citationStyle: CitationStyle;
  /** ツール活動内に推論過程（reasoning）ステップを表示するか。既定は非表示。 */
  showReasoning: boolean;
}

// ── Agent SSE stream protocol (server → client) ─────────────────────────────
export type AgentEvent =
  | { type: "step"; step: ToolCall }
  | { type: "answer-start" }
  | { type: "answer-delta"; text: string }
  | {
      type: "done";
      tokens: number;
      durationMs: number;
      citationMap: CitationMap;
      sourceIds: string[];
      sources: Source[];
      threadId: string;
      /** 回答不能時の理由。回答できたら null。分析のコンテンツギャップ検知に使う。 */
      noAnswerReason?: string | null;
    }
  /** 永続化完了。messageId はフィードバック送信に使う（chat-run が save 後に emit）。 */
  | { type: "saved"; messageId: string }
  | { type: "error"; message: string };
