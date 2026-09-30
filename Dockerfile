FROM python:3.14-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python (capa de cache)
COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

# Código fuente
COPY api/ ./api/
COPY start_coach_api.py ./
COPY backup.py ./
COPY *.html *.js *.css manifest.json sw.js ./

# Directorio de datos (montado como volumen en producción)
RUN mkdir -p data backups logs

# Usuario no-root
RUN useradd -m -u 1000 labxuser && chown -R labxuser:labxuser /app
USER labxuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "start_coach_api.py"]
