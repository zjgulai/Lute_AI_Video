import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  // P1-A: 业务文件禁止硬编码 demo API key + 禁止 import 已 deprecated 的 API_BASE 常量
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      // 白名单:这些文件允许出现 demo key 字符串(api.ts 默认值、placeholder、i18n 文案)
      "src/components/api.ts",
      "src/components/SettingsPanel.tsx",
      "src/i18n/translations.ts",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value='ai_video_demo_2026']",
          message:
            "禁止硬编码 demo API key。用 apiFetch() 或 getApiKey() — Settings 修改后才能立即生效。",
        },
      ],
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/components/api",
              importNames: ["API_BASE"],
              message:
                "API_BASE 是模块加载时常量,Settings 修改 base URL 后不刷新。改用 apiFetch() 或 getApiBase()。",
            },
            {
              name: "./api",
              importNames: ["API_BASE"],
              message:
                "API_BASE 是模块加载时常量,Settings 修改 base URL 后不刷新。改用 apiFetch() 或 getApiBase()。",
            },
          ],
        },
      ],
    },
  },
]);

export default eslintConfig;
