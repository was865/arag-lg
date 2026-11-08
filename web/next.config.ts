import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
