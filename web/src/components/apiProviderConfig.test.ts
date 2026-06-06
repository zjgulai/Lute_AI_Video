import { beforeEach, describe, expect, it } from "vitest";
import {
  getProviderApiKeysForRequest,
  resetApiConfig,
  setModelProviderConfig,
  withProviderApiKeys,
} from "./api";

describe("provider API key runtime config", () => {
  beforeEach(() => {
    localStorage.clear();
    resetApiConfig();
  });

  it("normalizes provider keys before exposing them to scenario requests", () => {
    setModelProviderConfig({
      apiKeys: {
        DEEPSEEK_API_KEY: "  deepseek-key  ",
        POYO_API_KEY: "poyo-key",
        SILICONFLOW_API_KEY: "",
      },
    });

    expect(getProviderApiKeysForRequest()).toEqual({
      DEEPSEEK_API_KEY: "deepseek-key",
      POYO_API_KEY: "poyo-key",
    });
  });

  it("injects configured provider keys without replacing explicit request keys", () => {
    setModelProviderConfig({
      apiKeys: {
        DEEPSEEK_API_KEY: "deepseek-key",
        POYO_API_KEY: "poyo-key",
      },
    });

    expect(withProviderApiKeys({
      product_catalog: { name: "X1" },
      api_keys: { OPENAI_API_KEY: "openai-key" },
    })).toEqual({
      product_catalog: { name: "X1" },
      api_keys: {
        OPENAI_API_KEY: "openai-key",
        DEEPSEEK_API_KEY: "deepseek-key",
        POYO_API_KEY: "poyo-key",
      },
    });
  });
});
