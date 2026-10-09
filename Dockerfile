FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TESSERACT_CMD=/usr/bin/tesseract \
    OMP_THREAD_LIMIT=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

RUN useradd --create-home capre \
    && mkdir -p /app/instance \
    && chown capre:capre /app/instance

COPY app ./app
COPY config.py run.py ./
COPY migrations ./migrations
COPY scripts/migrate.py ./scripts/migrate.py

USER capre
EXPOSE 10000

CMD ["sh", "-c", "exec gunicorn run:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 120"]
