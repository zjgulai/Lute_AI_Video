import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { translations, type Locale } from "./translations";

const SOURCE_ROOT = path.resolve(__dirname, "..");
const LOCALES = Object.keys(translations) as Locale[];

function listSourceFiles(dir: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") return [];
      return listSourceFiles(fullPath);
    }
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) return [];
    return [fullPath];
  });
}

function literalTranslationKeys(): string[] {
  const keys = new Set<string>();
  const staticKeyPattern = /\bt\(\s*["']([^"'`$+{}()]+)["']/g;

  for (const filePath of listSourceFiles(SOURCE_ROOT)) {
    const source = fs.readFileSync(filePath, "utf8");
    for (const match of source.matchAll(staticKeyPattern)) {
      const key = match[1];
      if (key && !key.endsWith(".")) keys.add(key);
    }
  }

  return Array.from(keys).sort();
}

describe("translation completeness", () => {
  it("keeps locale key sets identical", () => {
    const [baseLocale, ...otherLocales] = LOCALES;
    const baseKeys = Object.keys(translations[baseLocale]).sort();

    for (const locale of otherLocales) {
      expect(Object.keys(translations[locale]).sort()).toEqual(baseKeys);
    }
  });

  it("keeps literal t() keys backed by every locale", () => {
    const usedKeys = literalTranslationKeys();

    for (const locale of LOCALES) {
      const localeKeys = new Set(Object.keys(translations[locale]));
      const missing = usedKeys.filter((key) => !localeKeys.has(key));
      expect(missing, `${locale} is missing literal t() keys`).toEqual([]);
    }
  });

  it("keeps translation values non-empty and searchable", () => {
    for (const locale of LOCALES) {
      for (const [key, value] of Object.entries(translations[locale])) {
        expect(key.trim(), `${locale} key should not be empty`).toBe(key);
        expect(key, `${locale} key should not contain whitespace`).not.toMatch(/\s/);
        expect(value.trim(), `${locale}.${key} should not be empty`).not.toBe("");
      }
    }
  });
});
