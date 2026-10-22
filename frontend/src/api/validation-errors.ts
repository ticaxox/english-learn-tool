/**
 * Server-side validation issues (HTTP 422).
 *
 * FastAPI publishes this shape in `components.schemas.HTTPValidationError`
 * (`detail: ValidationError[]`, each with `loc`, `msg`, `type`). That schema is
 * part of the already-frozen baseline contract and is stable across the learning
 * endpoints, so parsing it is contract-independent work: nothing here needs a
 * T-BE-004 field name.
 *
 * What this module deliberately does NOT do: translate `loc` segments into UI
 * field names. The backend names its own fields, and inventing a mapping before
 * `contract_sha` is frozen is exactly the guessing the task forbids. Issues are
 * therefore surfaced verbatim (path + server message) and the mapping is added
 * later, in the single calibration point.
 */

export interface FieldValidationIssue {
  /** Dotted server location without the leading `body`/`query` segment. */
  path: string
  /** Server-authored message, never reworded by the frontend. */
  message: string
  /** Server error type, e.g. `value_error`; kept for diagnostics only. */
  type: string
}

/** Upper bound so a hostile or broken payload cannot flood the UI. */
export const MAX_VALIDATION_ISSUES = 20

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readLocation(loc: unknown): string {
  if (!Array.isArray(loc)) {
    return ''
  }
  return loc
    .filter((segment) => segment !== 'body' && segment !== 'query' && segment !== 'path')
    .map((segment) => (typeof segment === 'string' || typeof segment === 'number' ? String(segment) : ''))
    .filter((segment) => segment.length > 0)
    .join('.')
}

/**
 * Extract the documented FastAPI validation issues from an error payload.
 * Returns an empty array for any other payload, including a plain
 * `ErrorResponse` with `code`/`message`/`request_id`.
 */
export function parseValidationIssues(payload: unknown): FieldValidationIssue[] {
  if (!isRecord(payload) || !Array.isArray(payload.detail)) {
    return []
  }

  const issues: FieldValidationIssue[] = []
  for (const entry of payload.detail) {
    if (!isRecord(entry) || typeof entry.msg !== 'string') {
      continue
    }
    issues.push({
      path: readLocation(entry.loc),
      message: entry.msg,
      type: typeof entry.type === 'string' ? entry.type : 'unknown',
    })
    if (issues.length >= MAX_VALIDATION_ISSUES) {
      break
    }
  }
  return issues
}

/** True when the payload is the documented 422 validation envelope. */
export function isValidationPayload(payload: unknown): boolean {
  return isRecord(payload) && Array.isArray(payload.detail)
}
