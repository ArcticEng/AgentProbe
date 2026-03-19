FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml .
COPY agentprobe/ agentprobe/
COPY api/ api/
COPY billing/ billing/
COPY certification/ certification/
COPY .env.example .env.example

RUN pip install --no-cache-dir fastapi uvicorn stripe

EXPOSE 8000

# 4 workers = handles ~200 concurrent requests
# --timeout-keep-alive 30 = keeps connections alive for reuse
# --limit-concurrency 100 = per-worker concurrent request limit
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--timeout-keep-alive", "30", "--limit-concurrency", "100"]
