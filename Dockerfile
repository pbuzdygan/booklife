FROM python:3.14-alpine

ARG BOOKLIFE_UID=1000
ARG BOOKLIFE_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    BOOKLIFE_DATA_DIR=/app/data

WORKDIR /app

RUN addgroup -S -g "${BOOKLIFE_GID}" booklife \
    && adduser -S -D -H -u "${BOOKLIFE_UID}" -G booklife booklife

COPY requirements.lock /app/requirements.lock
RUN python -m pip install --requirement /app/requirements.lock \
    && python -c "import sqlite3; assert sqlite3.sqlite_version_info >= (3, 51, 3), sqlite3.sqlite_version"

COPY --chown=${BOOKLIFE_UID}:${BOOKLIFE_GID} . /app
RUN mkdir -p /app/data /app/staticfiles \
    && BOOKLIFE_DEBUG=false \
       BOOKLIFE_SECRET_KEY=booklife-build-only-static-files-key \
       python manage.py collectstatic --noinput \
    && chown -R "${BOOKLIFE_UID}:${BOOKLIFE_GID}" /app \
    && chmod -R a+rX /app \
    && chmod 0700 /app/data

USER ${BOOKLIFE_UID}:${BOOKLIFE_GID}
RUN test -r /app/manage.py \
    && test -r /app/booklife/wsgi.py \
    && python -c "import booklife.wsgi"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=3)"]

CMD ["sh", "-c", "python manage.py prepare_booklife && exec gunicorn booklife.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 30 --access-logfile -"]
