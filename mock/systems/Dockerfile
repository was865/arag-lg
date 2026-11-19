# 評価用の模擬の社内システム（specs/032）。4 つの MCP サーバを 8201〜8204 で出す。
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
RUN useradd --system --uid 10001 mock && mkdir -p /data && chown mock /data
USER mock
ENV PATH="/app/.venv/bin:$PATH" MOCK_DATA_DIR=/data
EXPOSE 8201 8202 8203 8204
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8201/healthz').status==200 else 1)"
CMD ["python", "-m", "mock_systems.main"]
