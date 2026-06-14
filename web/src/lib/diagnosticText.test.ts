import { describe, expect, it } from "vitest";

import { truncateDiagnosticText } from "./diagnosticText";

describe("truncateDiagnosticText", () => {
  it("preserves short text and truncates long text with ellipsis", () => {
    expect(truncateDiagnosticText("short text", 20)).toBe("short text");
    expect(truncateDiagnosticText("abcdefghijklmnopqrstuvwxyz", 10)).toBe("abcdefghi…");
  });
});
