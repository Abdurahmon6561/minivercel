# Render Docker runtime, free plan.

# ---- stage 1: build the dashboard -------------------------------------------
# Only reached to produce static files; nothing from this stage runs at
# request time. web/.env.production sets VITE_API_BASE_URL, so this needs no
# --build-arg plumbing - Vite loads it automatically for `vite build`.
FROM node:20-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# app/hostrouting.py serves this for Host: app.{SITE_DOMAIN} when
# URL_MODE=subdomain; ignored entirely in the default URL_MODE=path.
COPY --from=webbuild /web/dist ./web-dist
ENV DASHBOARD_DIST_DIR=/app/web-dist

# Never run as root. The container has no build toolchain, no shell utilities
# beyond the slim base, and nothing in it is ever invoked on user input.
RUN useradd --create-home --uid 10001 minivercel \
    && chown -R minivercel:minivercel /app
USER minivercel

# Render injects $PORT. 10000 is its default for Docker services.
ENV PORT=10000
EXPOSE 10000

# One worker: the free plan gives 0.1 CPU and 512 MB. The workload is almost
# entirely I/O wait on Supabase, which one async worker handles fine, and a
# second worker would double the memory floor for no throughput.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --timeout-keep-alive 65 --proxy-headers --forwarded-allow-ips '*'"]
