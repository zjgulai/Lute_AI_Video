import { describe, it, expect } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";

describe("vitest + react smoke test", () => {
  it("can render a simple React component", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    function Hello() {
      return <div>hello</div>;
    }

    const root = createRoot(container);
    await act(async () => {
      root.render(<Hello />);
    });
    expect(container.textContent).toBe("hello");
    root.unmount();
    document.body.removeChild(container);
  });
});
