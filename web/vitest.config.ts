import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      // `server-only` は react-server 条件外で import すると例外を投げるためテストでは空にする
      "server-only": fileURLToPath(new URL("./test/empty.ts", import.meta.url)),
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
