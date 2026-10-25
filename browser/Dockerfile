FROM python:3.14.9-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Preserve the existing persistent profile's owner when replacing the Playwright image.
RUN groupadd --gid 1001 pwuser && useradd --uid 1001 --gid 1001 --create-home pwuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.2.2 && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    apt-get install -y --no-install-recommends xauth && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /data/profile && chown pwuser:pwuser /data/profile
COPY service.py test_service.py ./
USER pwuser
ENV PROFILE_DIR=/data/profile
CMD ["xvfb-run", "-a", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
