import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const SRC_ROOT = join(process.cwd(), "src");
const RUNTIME_MEDIA_IMAGE = "components/RuntimeMediaImage.tsx";
const RUNTIME_MEDIA_CONSUMERS = [
  "app/works/page.tsx",
  "components/AssetCard.tsx",
  "components/OneShotResultView.tsx",
  "components/SceneSelector.tsx",
  "components/VideoWorkflow.tsx",
  "app/library/BrandKitTab.tsx",
  "app/library/MaterialsTab.tsx",
  "components/AssetLibrary.tsx",
  "components/AssetPickerModal.tsx",
  "components/GalleryGrid.tsx",
];

function listTsxFiles(dir: string): string[] {
  return readdirSync(dir)
    .flatMap((entry) => {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) return listTsxFiles(path);
      return path.endsWith(".tsx") ? [path] : [];
    });
}

function readSrcFile(path: string): string {
  return readFileSync(join(SRC_ROOT, path), "utf8");
}

describe("RuntimeMediaImage guardrails", () => {
  it("keeps raw img usage centralized in RuntimeMediaImage", () => {
    const offenders = listTsxFiles(SRC_ROOT)
      .map((path) => relative(SRC_ROOT, path))
      .filter((path) => path !== RUNTIME_MEDIA_IMAGE)
      .filter((path) => {
        const source = readSrcFile(path);
        return source.includes("<img") || source.includes("@next/next/no-img-element");
      });

    expect(offenders).toEqual([]);
  });

  it("keeps known runtime-media consumers on RuntimeMediaImage", () => {
    for (const path of RUNTIME_MEDIA_CONSUMERS) {
      const source = readSrcFile(path);
      expect(source, `${path} should use RuntimeMediaImage for backend/user media`).toContain("RuntimeMediaImage");
    }
  });

  it("documents why the single raw img exception exists", () => {
    const source = readSrcFile(RUNTIME_MEDIA_IMAGE);

    expect(source).toContain("@next/next/no-img-element");
    expect(source).toContain("Runtime media URLs come from backend/user assets");
    expect(source).toContain("not guaranteed to be statically allowlisted for next/image");
  });
});
