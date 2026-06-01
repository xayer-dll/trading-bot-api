FROM python:3.11-slim

WORKDIR /app

# Sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# uv kur
RUN pip install uv

# Bağımlılıkları kur (cache için önce sadece pyproject.toml kopyala)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Kaynak kodları kopyala
COPY . .

# Port
EXPOSE 8080

# Başlat
CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
