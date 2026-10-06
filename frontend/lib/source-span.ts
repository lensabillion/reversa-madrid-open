/** A quoted stretch of one record's field; offsets count Unicode code points. */
type SpanField = "text" | "old_text" | "new_text" | "justification";
export interface SourceSpan {
  record_id: string;
  field: SpanField;
  start: number;
  end: number;
  text: string;
  page: number | null;
}
