/**
 * Type-safe error message extraction for unknown-typed catch blocks.
 *
 * Replaces `catch (e: unknown) { e.message }` (eslint no-explicit-any)
 * with `catch (e: unknown) { errorMessage(e) }`. The fallback parameter
 * lets callers customize what shows when the thrown value is not an Error
 * (e.g. a string, number, or null).
 *
 * @example
 *   try { ... } catch (e: unknown) { alert(errorMessage(e, "Failed to save")); }
 */
export function errorMessage(err: unknown, fallback = "Unknown error"): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    const m = (err as { message: unknown }).message;
    if (typeof m === "string") return m;
  }
  return fallback;
}
