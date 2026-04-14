FROM python:3.11-slim

# Install system dependencies for mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install ML worker dependencies
COPY ml_worker/requirements.txt ml_worker/requirements.txt
RUN pip install --no-cache-dir -r ml_worker/requirements.txt

# Install backend dependencies so Django ORM is available
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy ML worker and backend source (ml-worker needs config.settings)
COPY ml_worker/ ml_worker/
COPY backend/ backend/

# Put backend on the Python path so `config` module is importable
ENV PYTHONPATH="/app/backend:${PYTHONPATH}"

CMD ["celery", "-A", "config", "worker", "--loglevel=info", "--concurrency=2"]
