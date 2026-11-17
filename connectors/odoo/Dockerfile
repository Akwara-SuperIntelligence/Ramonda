FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
ENV UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY connectors/ ./
RUN uv sync --frozen --package odoo --no-dev
RUN useradd --system --uid 10002 --user-group --home-dir /app --no-create-home --shell /usr/sbin/nologin odoo
USER odoo
EXPOSE 8000
CMD ["python", "-m", "odoo"]
