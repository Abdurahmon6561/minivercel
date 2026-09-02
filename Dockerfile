# Render Docker runtime, free plan.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

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
