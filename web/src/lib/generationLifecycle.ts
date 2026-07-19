export type GenerationDisplayState = "full" | "bounded" | "error";

export type GenerationLifecycleLike = {
  status?: unknown;
  lifecycle_status?: unknown;
  completion_kind?: unknown;
  request_succeeded?: unknown;
  success?: unknown;
  full_media_success?: unknown;
};

/** Preserve bounded completion without promoting it to full success or failure. */
export function classifyGenerationResult(
  value: object,
): GenerationDisplayState {
  const result = value as GenerationLifecycleLike;
  const status = typeof result.status === "string" ? result.status : "";
  const lifecycleStatus = typeof result.lifecycle_status === "string"
    ? result.lifecycle_status
    : "";
  const completionKind = typeof result.completion_kind === "string"
    ? result.completion_kind
    : "";

  if (
    status === "error"
    || lifecycleStatus === "error"
    || completionKind === "execution_failed"
    || result.request_succeeded === false
  ) {
    return "error";
  }

  if (
    status === "completed_bounded"
    || lifecycleStatus === "completed_bounded"
    || completionKind === "no_media"
    || completionKind === "bounded_media"
    || (
      result.request_succeeded === true
      && result.full_media_success === false
    )
  ) {
    return "bounded";
  }

  if (
    status === "completed_full"
    || lifecycleStatus === "completed_full"
    || completionKind === "full_media"
    || result.full_media_success === true
  ) {
    return result.success === false ? "error" : "full";
  }

  if (result.success === false) return "error";

  // Legacy successful results predate lifecycle fields.
  return "full";
}
