# ERP の MCP サーバ（specs/033）。:8211 で Streamable HTTP を出す。
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY config ./config
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
RUN useradd --system --uid 10001 erp && mkdir -p /data && chown erp /data
USER erp
ENV PATH="/app/.venv/bin:$PATH" ERP_CONFIG_DIR=/app/config ERP_AUDIT_PATH=/data/audit.jsonl
EXPOSE 8211
HEALTHCHECK --interval=5s --timeout=3s --retries=30 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8211/healthz').status==200 else 1)"
CMD ["python", "-m", "erp_mcp.main"]
