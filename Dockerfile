FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend
WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY frontend /app/frontend
COPY docs /app/docs
COPY README.md /app/README.md
RUN mkdir -p /app/backend/data && chown -R app:app /app
USER app
# The container sits behind the host nginx proxy (compose publishes the port on loopback only), so trust its
# X-Forwarded-* headers. Without this, every client appears to come from the proxy and HTTPS is not detected.
ENV FORWARDED_ALLOW_IPS="*"
EXPOSE 8000
# One worker by default. Login throttling is shared through Redis (compose), so you may raise WEB_CONCURRENCY;
# the /api/metrics counters stay per-process (see docs/GO-LIVE.md).
ENV WEB_CONCURRENCY=1

CMD ["sh", "-c", "python -m uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
