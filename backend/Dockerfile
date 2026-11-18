FROM python:3.14.9-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8 AS deps

WORKDIR /app

# CVE-2026-109518: patch APT before installing packages; disable retries while patching.
RUN apt-get -o Acquire::Retries=0 update && \
    apt-get -o Acquire::Retries=0 install -y --no-install-recommends --only-upgrade apt libapt-pkg7.0 && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' apt)" ge 3.0.4 && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libapt-pkg7.0)" ge 3.0.4 && \
    apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.2.2 && pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 1001 nestswipe && \
    useradd --no-log-init --uid 1001 --gid 1001 --create-home nestswipe

ARG GIT_REVISION
LABEL org.opencontainers.image.source="https://github.com/ThomsCody/nestswipe" \
      org.opencontainers.image.revision="${GIT_REVISION}" \
      com.datadoghq.image.source_path="backend/Dockerfile"

FROM deps AS prod

COPY . .

USER 1001:1001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).close()"]

CMD ["ddtrace-run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "log_config.yaml"]

FROM deps AS test

COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

COPY . .

USER 1001:1001

HEALTHCHECK NONE
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-o", "cache_dir=/tmp/pytest-cache"]
