FROM python:3.11-slim

# SHA256 of the model weights file (pytorch_model.bin or model.safetensors).
# Pass the correct value at build time:
#   docker build --build-arg MODEL_SHA256=<actual_sha256> ...
# If left empty, the checksum step logs the actual value but does not fail the build,
# allowing the first build to capture the hash for subsequent pinning.
ARG MODEL_SHA256=""

# Install system dependencies for mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install NLP worker dependencies
COPY nlp_worker/requirements.txt nlp_worker/requirements.txt
RUN pip install --no-cache-dir -r nlp_worker/requirements.txt

# Install backend dependencies so Django ORM is available
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy NLP worker and backend source
COPY nlp_worker/ nlp_worker/
COPY backend/ backend/

# Put backend on the Python path so `config` module is importable
ENV PYTHONPATH="/app/backend:${PYTHONPATH}"

# Set the local model cache directory
ENV SENTENCE_TRANSFORMERS_HOME=/app/nlp_worker/models

# Download and bake in the sentence-transformer model at build time,
# then verify the SHA256 checksum of the main weights file.
# No network requests will be made during inference.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')" \
    && MODEL_DIR="${SENTENCE_TRANSFORMERS_HOME}/sentence-transformers_paraphrase-multilingual-MiniLM-L12-v2" \
    && WEIGHTS_FILE="${MODEL_DIR}/pytorch_model.bin" \
    && SAFE_FILE="${MODEL_DIR}/model.safetensors" \
    && if [ -f "${SAFE_FILE}" ]; then ACTUAL=$(sha256sum "${SAFE_FILE}" | awk '{print $1}'); \
       elif [ -f "${WEIGHTS_FILE}" ]; then ACTUAL=$(sha256sum "${WEIGHTS_FILE}" | awk '{print $1}'); \
       else echo "ERROR: model weights file not found" && exit 1; fi \
    && echo "Model weights SHA256: ${ACTUAL}" \
    && if [ -z "${MODEL_SHA256}" ]; then \
         echo "INFO: MODEL_SHA256 not set. Actual checksum is ${ACTUAL}. Pin it with --build-arg MODEL_SHA256=${ACTUAL}"; \
       elif [ "${ACTUAL}" != "${MODEL_SHA256}" ]; then \
         echo "ERROR: SHA256 mismatch — expected ${MODEL_SHA256}, got ${ACTUAL}" && exit 1; \
       else echo "SHA256 checksum verified OK."; fi

CMD ["celery", "-A", "config", "worker", "--loglevel=info", "--concurrency=2", "-Q", "nlp"]
