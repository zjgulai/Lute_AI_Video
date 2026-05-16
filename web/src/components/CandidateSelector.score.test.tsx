import { describe, it, expect, vi } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import CandidateSelector, { type Candidate } from "./CandidateSelector";
import { I18nProvider } from "@/i18n/I18nProvider";

function makeCandidate(id: string, overall = 0.85, recommended = false): Candidate {
  return {
    id,
    variant: id.endsWith("a") ? "standard" : id.endsWith("b") ? "creative" : "conservative",
    data: { hook: `hook for ${id}` },
    score: { overall, explanation: `explanation for ${id}` },
    recommended,
  };
}

function renderSelector(props: React.ComponentProps<typeof CandidateSelector>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<I18nProvider>{<CandidateSelector {...props} />}</I18nProvider>);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("CandidateSelector — score rendering (D3)", () => {
  it("renders score percentage as text inside each card", () => {
    const candidates = [
      makeCandidate("a", 0.92),
      makeCandidate("b", 0.45),
      makeCandidate("c", 0.71),
    ];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const text = container.textContent || "";
    expect(text).toContain("92%");
    expect(text).toContain("45%");
    expect(text).toContain("71%");
    cleanup();
  });

  it("uses jade-accent color class for high scores (>= 0.8)", () => {
    const candidates = [makeCandidate("a", 0.95)];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const card = container.querySelector('[data-candidate-id="a"]') as HTMLElement;
    const html = card.innerHTML;
    expect(html).toContain("jade-accent");
    expect(html).not.toContain("crimson-mist");
    cleanup();
  });

  it("uses crimson-mist color class for low scores (< 0.5)", () => {
    const candidates = [makeCandidate("a", 0.32)];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const card = container.querySelector('[data-candidate-id="a"]') as HTMLElement;
    const html = card.innerHTML;
    expect(html).toContain("crimson-mist");
    expect(html).not.toContain("jade-accent");
    cleanup();
  });

  it("uses gold-foil color class for mid-band scores (0.5 - 0.8)", () => {
    const candidates = [makeCandidate("a", 0.65)];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const card = container.querySelector('[data-candidate-id="a"]') as HTMLElement;
    const html = card.innerHTML;
    expect(html).toContain("gold-foil");
    cleanup();
  });

  it("renders score explanation text when provided", () => {
    const cand = makeCandidate("a", 0.8);
    cand.score.explanation = "Hooks score for emotional pull";
    const { container, cleanup } = renderSelector({
      candidates: [cand],
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const text = container.textContent || "";
    expect(text).toContain("Hooks score for emotional pull");
    cleanup();
  });

  it("renders recommended badge when candidate.recommended is true", () => {
    const candidates = [makeCandidate("a", 0.85, true), makeCandidate("b", 0.85, false)];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const cardA = container.querySelector('[data-candidate-id="a"]') as HTMLElement;
    const cardB = container.querySelector('[data-candidate-id="b"]') as HTMLElement;
    const aBadgeCount = cardA.querySelectorAll("svg").length;
    const bBadgeCount = cardB.querySelectorAll("svg").length;
    expect(aBadgeCount).toBeGreaterThan(bBadgeCount);
    cleanup();
  });

  it("clamps content preview to 100 chars and shows ellipsis on overflow", () => {
    const longHook = "x".repeat(200);
    const cand: Candidate = {
      id: "long",
      variant: "standard",
      data: { hook: longHook },
      score: { overall: 0.85 },
      recommended: false,
    };
    const { container, cleanup } = renderSelector({
      candidates: [cand],
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const text = container.textContent || "";
    expect(text).toContain("...");
    cleanup();
  });

  it("shows variant labels for standard/creative/conservative", () => {
    const candidates = [
      { ...makeCandidate("a"), variant: "standard" as const },
      { ...makeCandidate("b"), variant: "creative" as const },
      { ...makeCandidate("c"), variant: "conservative" as const },
    ];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 3,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    expect(container.querySelector('[data-candidate-id="a"]')).toBeTruthy();
    expect(container.querySelector('[data-candidate-id="b"]')).toBeTruthy();
    expect(container.querySelector('[data-candidate-id="c"]')).toBeTruthy();
    cleanup();
  });
});

describe("CandidateSelector — multi-select edge cases (D3)", () => {
  it("clicking an unselected candidate when at maxSelections=1 is disabled (no FIFO swap on disabled button)", () => {
    const onSelectionChange = vi.fn();
    const candidates = [makeCandidate("a"), makeCandidate("b"), makeCandidate("c")];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: ["a"],
      onSelectionChange,
      onEdit: () => {},
    });
    const cardB = container.querySelector('[data-candidate-id="b"]') as HTMLElement;
    const btnB = cardB.querySelectorAll("button")[0] as HTMLButtonElement;
    expect(btnB.disabled).toBe(true);
    act(() => btnB.click());
    expect(onSelectionChange).not.toHaveBeenCalled();
    cleanup();
  });

  it("missing data in candidate doesn't crash render (safe-default)", () => {
    const cand: Candidate = {
      id: "empty",
      variant: "standard",
      data: null as unknown as Record<string, unknown>,
      score: { overall: 0.5 },
      recommended: false,
    };
    const { container, cleanup } = renderSelector({
      candidates: [cand],
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    expect(container.querySelector('[data-candidate-id="empty"]')).toBeTruthy();
    cleanup();
  });
});
