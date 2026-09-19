FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY app.py .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8801", "--timeout-graceful-shutdown", "310"]

