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
  assetPrefix: assetPrefix || undefined,
  trailingSlash: isGhPages ? true : undefined,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
