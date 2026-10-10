FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    mkdir -p /data/profile && chown pwuser:pwuser /data/profile
COPY service.py test_service.py ./
USER pwuser
ENV PROFILE_DIR=/data/profile
CMD ["xvfb-run", "-a", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
