# ARag API（FastAPI）。uv でロックどおりに依存を入れ、非 root で動かす。
FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# 依存だけ先に入れてレイヤキャッシュを効かせる
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

RUN useradd --system --uid 10001 arag
USER arag
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["uvicorn", "arag.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
