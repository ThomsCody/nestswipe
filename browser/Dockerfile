FROM python:3.14.9-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# CVE-2026-109518: patch APT before Playwright installs its system dependencies.
RUN apt-get -o Acquire::Retries=0 update && \
    apt-get -o Acquire::Retries=0 install -y --no-install-recommends --only-upgrade apt libapt-pkg7.0 && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' apt)" ge 3.0.4 && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libapt-pkg7.0)" ge 3.0.4 && \
    rm -rf /var/lib/apt/lists/*

# Preserve the existing persistent profile's owner when replacing the Playwright image.
RUN groupadd --gid 1001 pwuser && useradd --no-log-init --uid 1001 --gid 1001 --create-home pwuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.2.2 && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    apt-get install -y --no-install-recommends xauth && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /data/profile && chown pwuser:pwuser /data/profile
COPY service.py test_service.py ./
ARG GIT_REVISION
LABEL org.opencontainers.image.source="https://github.com/ThomsCody/nestswipe" \
      org.opencontainers.image.revision="${GIT_REVISION}" \
      com.datadoghq.image.source_path="browser/Dockerfile"
USER pwuser
ENV PROFILE_DIR=/data/profile
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]
CMD ["xvfb-run", "-a", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
