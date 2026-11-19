import type { NextConfig } from "next";

// 別の入口（ARAG_EXTRA_ORIGINS。Tailscale など）から開いても next dev の資源を使えるように（ホスト名だけで照合）
const extraDevHosts = (process.env.ARAG_EXTRA_ORIGINS ?? "")
  .split(",")
  .flatMap((s) => {
    try {
      return [new URL(s.trim()).hostname];
    } catch {
      return [];
    }
  });

const nextConfig: NextConfig = {
  allowedDevOrigins: extraDevHosts,
  // Docker 用に依存を同梱した最小サーバを出力する
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
