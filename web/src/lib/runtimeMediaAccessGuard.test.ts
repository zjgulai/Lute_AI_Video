import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_ROOT = join(process.cwd(), "src");
const MEDIA_WRAPPERS = new Set([
  "components/RuntimeMediaImage.tsx",
  "components/RuntimeMediaVideo.tsx",
  "components/RuntimeMediaAudio.tsx",
  "components/RuntimeMediaLink.tsx",
]);

function listTsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return listTsxFiles(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

function unsafeDomAttributes(source: string): string[] {
  const domOpenings = source.match(/<(?:img|video|audio|a)\b[^>]*>/g) ?? [];
  return domOpenings.filter((opening) => {
    const callsUnsignedBuilder = /\b(?:src|href)\s*=\s*\{\s*getMediaUrl\s*\(/.test(opening);
    const embedsProtectedPath = /\b(?:src|href)\s*=\s*(?:\{[^}]*|["'`])\/api\/media\//.test(opening);
    return callsUnsignedBuilder || embedsProtectedPath;
  });
}

describe("runtime media access guardrails", () => {
  it.each([
    ["components/RuntimeMediaImage.tsx", "src={url}", 'useSignedMediaUrl(src, "view")'],
    ["components/RuntimeMediaVideo.tsx", "src={url}", 'useSignedMediaUrl(src, "view")'],
    ["components/RuntimeMediaAudio.tsx", "src={url}", 'useSignedMediaUrl(src, "view")'],
    ["components/RuntimeMediaLink.tsx", "href={url}", 'useSignedMediaUrl(href, resolvedPurpose)'],
  ])("routes %s through the signed-media hook", (path, domBinding, hookCall) => {
    const source = readFileSync(join(SRC_ROOT, path), "utf8");

    expect(source).toContain(hookCall);
    expect(source).toContain("if (!url) return null");
    expect(source).toContain(domBinding);
  });

  it("keeps unsigned protected media URLs out of DOM attributes", () => {
    const offenders = listTsxFiles(SRC_ROOT)
      .map((path) => relative(SRC_ROOT, path))
      .filter((path) => !MEDIA_WRAPPERS.has(path))
      .flatMap((path) => {
        const openings = unsafeDomAttributes(readFileSync(join(SRC_ROOT, path), "utf8"));
        return openings.map((opening) => `${path}: ${opening.replace(/\s+/g, " ").slice(0, 160)}`);
      });

    expect(offenders).toEqual([]);
  });

  it("centralizes portfolio library media and guards mixed fast-mode previews", () => {
    const assetLibrary = readFileSync(join(SRC_ROOT, "components/AssetLibrary.tsx"), "utf8");
    expect(assetLibrary).toContain("RuntimeMediaVideo");
    expect(assetLibrary).toContain("RuntimeMediaAudio");
    expect(assetLibrary).toContain("RuntimeMediaLink");
    expect(assetLibrary).not.toContain("<video");
    expect(assetLibrary).not.toContain("<audio");

    const fastMode = readFileSync(join(SRC_ROOT, "components/FastModePanel.tsx"), "utf8");
    expect(fastMode).toContain("resolveMediaPreview(result.video_url)");
    expect(fastMode).toContain("<RuntimeMediaVideo");
    expect(fastMode).toContain("<video");
    expect(fastMode).not.toContain("src={result.video_url}");
  });

  it("keeps compare-view downloads inside the signed link wrapper", () => {
    const compareView = readFileSync(join(SRC_ROOT, "components/CompareView.tsx"), "utf8");

    expect(compareView).toContain("RuntimeMediaLink");
    expect(compareView).not.toContain("onDownload");
  });

  it("rejects imperative unsigned media window opens", () => {
    const offenders = listTsxFiles(SRC_ROOT)
      .map((path) => relative(SRC_ROOT, path))
      .filter((path) => readFileSync(join(SRC_ROOT, path), "utf8").includes("window.open(getMediaUrl("));

    expect(offenders).toEqual([]);
  });
});
