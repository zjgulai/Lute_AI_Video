import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

// Next 16 default bundler: Turbopack can mis-infer the workspace root (e.g. treat `src/app` as root)
// and then fail to resolve `next/package.json`. Pin root to this package directory.
const WEB_ROOT = path.dirname(fileURLToPath(import.meta.url));

// Deployment target: gh-pages | cloudbase | standalone
const deployTarget = process.env.DEPLOY_TARGET || "standalone";
const isGhPages = deployTarget === "gh-pages";
const isCloudBase = deployTarget === "cloudbase";
const repoName = "Lute_AI_Video";

const assetPrefix = isGhPages ? `/${repoName}` : "";

// Inject prefix for public folder assets at build time
process.env.NEXT_PUBLIC_ASSET_PREFIX = assetPrefix;

const nextConfig: NextConfig = {
  output: isGhPages || isCloudBase ? "export" : "standalone",
  distDir: isGhPages || isCloudBase ? "dist" : ".next",
  basePath: isGhPages ? `/${repoName}` : "",
  // CloudBase static hosting requires trailingSlash for clean SPA-like routing
  trailingSlash: isGhPages || isCloudBase ? true : undefined,
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: WEB_ROOT,
  },
};

export default nextConfig;
