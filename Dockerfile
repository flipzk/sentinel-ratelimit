FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e .


RUN pip install structlog

CMD ["uvicorn", "sentinel.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]