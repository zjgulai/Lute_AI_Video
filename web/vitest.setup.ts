import { expect } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";

// Extend vitest expect with jest-dom matchers (toBeInTheDocument, etc.)
expect.extend(matchers as unknown as Parameters<typeof expect.extend>[0]);

// React 19 requires an explicit act environment flag for createRoot-based tests.
(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
