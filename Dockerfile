FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY app ./app
COPY config ./config
COPY migrations ./migrations
COPY templates ./templates
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/artifacts \
    && chown -R appuser:appuser /app /usr/local/bin/docker-entrypoint \
    && chmod 0755 /usr/local/bin/docker-entrypoint

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

ENTRYPOINT ["docker-entrypoint"]
