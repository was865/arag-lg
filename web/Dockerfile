# ARag Web（Next.js 16, standalone 出力）。非 root で動かす。
FROM node:24-slim AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile

FROM node:24-slim AS build
WORKDIR /app
RUN corepack enable
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:24-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN useradd --system --uid 10001 arag
COPY --from=build --chown=arag /app/.next/standalone ./
COPY --from=build --chown=arag /app/.next/static ./.next/static
COPY --from=build --chown=arag /app/public ./public
USER arag
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
