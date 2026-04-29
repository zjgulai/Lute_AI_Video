import type { NextConfig } from "next";

// GitHub Pages project page uses repo-name as subpath
const repoName = "Lute_AI_Video";
const isGhPages = process.env.DEPLOY_TARGET === "gh-pages";
const assetPrefix = isGhPages ? `/${repoName}` : "";

// Inject prefix for public folder assets at build time
process.env.NEXT_PUBLIC_ASSET_PREFIX = assetPrefix;

const nextConfig: NextConfig = {
  output: isGhPages ? "export" : "standalone",
  distDir: isGhPages ? "dist" : ".next",
  basePath: isGhPages ? `/${repoName}` : "",
  // assetPrefix is intentionally omitted — basePath already handles _next/static paths.
  // NEXT_PUBLIC_ASSET_PREFIX is kept for manual <img src> references in components.
  trailingSlash: isGhPages ? true : undefined,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
