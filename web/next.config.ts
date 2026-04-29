import type { NextConfig } from "next";

// GitHub Pages project page uses repo-name as subpath
const repoName = "Lute_AI_Video";
const isGhPages = process.env.DEPLOY_TARGET === "gh-pages";

const nextConfig: NextConfig = {
  output: isGhPages ? "export" : "standalone",
  distDir: isGhPages ? "dist" : ".next",
  assetPrefix: isGhPages ? `/${repoName}` : undefined,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
