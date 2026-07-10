import { describe, expect, it } from "vitest";
import { getGateSequence } from "./GateDirectAccess";

const translate = (key: string, fallback?: string) => fallback || key;

describe("getGateSequence", () => {
  it("matches the backend S3 gate identifiers", () => {
    expect(getGateSequence("s3", translate).map((gate) => gate.gateId)).toEqual([
      "gate_1_script",
      "gate_2_keyframe",
      "gate_3_clips",
      "gate_4_final",
    ]);
  });

  it("matches the backend S4 gate identifiers", () => {
    expect(getGateSequence("s4", translate).map((gate) => gate.gateId)).toEqual([
      "gate_1_script",
      "gate_2_prompts",
      "gate_3_thumbnails",
    ]);
  });

  it("matches the backend S5 gate identifiers", () => {
    expect(getGateSequence("s5", translate).map((gate) => gate.gateId)).toEqual([
      "gate_1_strategy",
      "gate_2_clips",
      "gate_3_final",
    ]);
  });
});
