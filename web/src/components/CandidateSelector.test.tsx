import { describe, it, expect, vi } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import CandidateSelector, { normalizeCandidates, type Candidate } from "./CandidateSelector";
import { I18nProvider } from "@/i18n/I18nProvider";

function makeCandidate(id: string, overall = 0.85, recommended = false): Candidate {
  return {
    id,
    variant: id.endsWith("a") ? "standard" : id.endsWith("b") ? "creative" : "conservative",
    data: { hook: `hook for ${id}` },
    score: { overall, explanation: "ok" },
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
    rerender: (next: React.ComponentProps<typeof CandidateSelector>) => {
      act(() => {
        root.render(<I18nProvider>{<CandidateSelector {...next} />}</I18nProvider>);
      });
    },
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("CandidateSelector", () => {
  it("normalizes backend candidate payloads before they enter the UI contract", () => {
    const normalized = normalizeCandidates([
      {
        id: "  ",
        variant: "experimental",
        data: { hook: "demo", missing: undefined, nested: { enabled: true } },
        score: {
          overall: 1.8,
          explanation: 42,
          breakdown: { director_intent: "bad", continuity: 0.7 },
        },
        recommended: "yes",
      },
      null,
    ]);

    expect(normalized).toHaveLength(1);
    expect(normalized[0]).toMatchObject({
      id: "candidate-1",
      variant: "standard",
      data: { hook: "demo", missing: null, nested: { enabled: true } },
      score: { overall: 1, breakdown: { continuity: 0.7 } },
      recommended: false,
    });
  });

  it("renders 3 skeleton placeholders when candidates list is empty", () => {
    const { container, cleanup } = renderSelector({
      candidates: [],
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit: () => {},
    });
    const cards = container.querySelectorAll(".apple-card, [data-skeleton], [class*=animate-pulse]");
    expect(cards.length).toBeGreaterThanOrEqual(3);
    cleanup();
  });

  function selectButtonFor(container: HTMLElement, id: string): HTMLElement {
    const card = container.querySelector(`[data-candidate-id="${id}"]`);
    if (!card) throw new Error(`no card with id=${id}`);
    const buttons = card.querySelectorAll("button");
    // first button is the "Select" toggle; second is "Edit"
    return buttons[0] as HTMLElement;
  }

  it("calls onSelectionChange with the candidate id when an unselected card's Select button is clicked", () => {
    const onSelectionChange = vi.fn();
    const candidates = [makeCandidate("a"), makeCandidate("b"), makeCandidate("c")];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange,
      onEdit: () => {},
    });
    act(() => selectButtonFor(container, "a").click());
    expect(onSelectionChange).toHaveBeenCalledWith(["a"]);
    cleanup();
  });

  it("removes id from selection when a selected card's Select button is clicked again (toggle off)", () => {
    const onSelectionChange = vi.fn();
    const candidates = [makeCandidate("a"), makeCandidate("b"), makeCandidate("c")];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 2,
      selectedIds: ["a"],
      onSelectionChange,
      onEdit: () => {},
    });
    act(() => selectButtonFor(container, "a").click());
    expect(onSelectionChange).toHaveBeenCalledWith([]);
    cleanup();
  });

  it("disables the Select button on unselected cards when at maxSelections", () => {
    const onSelectionChange = vi.fn();
    const candidates = [makeCandidate("a"), makeCandidate("b"), makeCandidate("c")];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 2,
      selectedIds: ["a", "b"],
      onSelectionChange,
      onEdit: () => {},
    });
    const btnC = selectButtonFor(container, "c") as HTMLButtonElement;
    expect(btnC.disabled).toBe(true);
    act(() => btnC.click());
    expect(onSelectionChange).not.toHaveBeenCalled();
    const btnA = selectButtonFor(container, "a") as HTMLButtonElement;
    expect(btnA.disabled).toBe(false);
    cleanup();
  });

  it("invokes onEdit with the candidate id when the Edit button is clicked", () => {
    const onEdit = vi.fn();
    const candidates = [makeCandidate("a"), makeCandidate("b"), makeCandidate("c")];
    const { container, cleanup } = renderSelector({
      candidates,
      maxSelections: 1,
      selectedIds: [],
      onSelectionChange: () => {},
      onEdit,
    });
    const card = container.querySelector('[data-candidate-id="b"]') as HTMLElement;
    const editBtn = card.querySelectorAll("button")[1] as HTMLElement;
    act(() => editBtn.click());
    expect(onEdit).toHaveBeenCalledWith("b");
    cleanup();
  });
});
