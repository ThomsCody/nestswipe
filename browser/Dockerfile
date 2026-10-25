FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# Refresh the pinned browser image's operating-system security packages.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.2.2 filelock==4.2.4 virtualenv==21.14.13 && \
    pip install --no-cache-dir -r requirements.txt && \
    mkdir -p /data/profile && chown pwuser:pwuser /data/profile
COPY service.py test_service.py ./
USER pwuser
ENV PROFILE_DIR=/data/profile
CMD ["xvfb-run", "-a", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
