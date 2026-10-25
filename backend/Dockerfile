FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS deps

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.2.2 && pip install --no-cache-dir -r requirements.txt

FROM deps AS prod

COPY . .

CMD ["ddtrace-run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "log_config.yaml"]

FROM deps AS test

COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
