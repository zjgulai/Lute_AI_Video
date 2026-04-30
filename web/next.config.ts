import type { NextConfig } from "next";

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
};

export default nextConfig;
