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

  it("does not expose disabled or unknown provider keys in request payloads", () => {
    localStorage.setItem("ai_video_provider_config", JSON.stringify({
      apiKeys: {
        DEEPSEEK_API_KEY: "deepseek-key",
        POYO_API_KEY: "poyo-key",
        NOT_REGISTERED_API_KEY: "must-not-leak",
      },
      enabledProviders: {
        DEEPSEEK_API_KEY: true,
        POYO_API_KEY: false,
        NOT_REGISTERED_API_KEY: true,
      },
    }));

    expect(getProviderApiKeysForRequest()).toEqual({
      DEEPSEEK_API_KEY: "deepseek-key",
    });
    expect(withProviderApiKeys({ prompt: "audit" })).toEqual({
      prompt: "audit",
      api_keys: {
        DEEPSEEK_API_KEY: "deepseek-key",
      },
    });
  });

  it("leaves request bodies unchanged when configured keys are empty or disabled", () => {
    setModelProviderConfig({
      apiKeys: {
        DEEPSEEK_API_KEY: "",
        POYO_API_KEY: "poyo-key",
      },
      enabledProviders: {
        POYO_API_KEY: false,
      },
    });

    const body = { product_catalog: { name: "X1" } };
    expect(getProviderApiKeysForRequest()).toEqual({});
    expect(withProviderApiKeys(body)).toBe(body);
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
