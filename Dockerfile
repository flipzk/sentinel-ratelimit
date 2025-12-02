FROM python:3.11-slim

WORKDIR /app

# Instalar utilitários de sistema
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 1. Copiar ficheiros de configuração
COPY pyproject.toml README.md ./

# 2. Copiar o código fonte (CRUCIAL: Isto tem de acontecer ANTES do pip install)
COPY src ./src

# 3. Instalar o projeto e dependências
RUN pip install --no-cache-dir -e .

# 4. Comando de arranque
CMD ["uvicorn", "sentinel.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]