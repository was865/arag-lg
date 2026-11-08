/** フィードバックの許容値と共有型（依存ゼロ。API/queries/UI で共用）。 */

export const FEEDBACK_RATINGS = ["up", "down"] as const;
export type FeedbackRating = (typeof FEEDBACK_RATINGS)[number];

/** 👎 の理由タグ。複数選択。up のときは常に空配列。 */
export const FEEDBACK_REASON_TAGS = ["outdated", "wrong", "no_source", "irrelevant", "other"] as const;
export type FeedbackReasonTag = (typeof FEEDBACK_REASON_TAGS)[number];

/** Turn / API が運ぶ永続フィードバックのスナップショット。 */
export interface TurnFeedback {
  rating: FeedbackRating;
  reasonTags: FeedbackReasonTag[];
  comment: string | null;
}
