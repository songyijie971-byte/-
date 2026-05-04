# Classroom demo application container.

FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -r app && useradd -r -g app app

COPY --chown=app:app . .

RUN mkdir -p /app/data/uploads \
    /app/data/alerts \
    /app/data/model \
    /app/data/job_queue/pending \
    /app/data/job_queue/processing \
    /app/data/job_queue/done \
    /app/data/job_queue/failed \
    /app/data/runtime \
    && chown -R app:app /app/data

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)" || exit 1

CMD ["python", "app.py"]
