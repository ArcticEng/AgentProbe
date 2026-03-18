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
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
