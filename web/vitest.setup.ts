import { expect } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";

// Extend vitest expect with jest-dom matchers (toBeInTheDocument, etc.)
expect.extend(matchers as unknown as Parameters<typeof expect.extend>[0]);
