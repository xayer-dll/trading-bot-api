FROM python:3.11-slim

WORKDIR /app

# Sistem bagimliliklari
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# uv kur
RUN pip install uv

# Bagimliliklari kur (cache icin once sadece pyproject.toml kopyala)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Kaynak kodlari kopyala
COPY . .

# SQLite verisi icin dizin
RUN mkdir -p /data
ENV DB_PATH=/data/trading_bot.db

# Log dizini
RUN mkdir -p /app/logs

# Port
EXPOSE 8080

# Baslat
CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
