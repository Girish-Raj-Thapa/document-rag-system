FROM python:3.11-slim

# ── System dependencies for unstructured.io, Tesseract OCR, and pgvector ──
# These are large but necessary for PDF parsing and layout analysis
RUN apt-get update && apt-get install -y --no-install-recommends \
    # unstructured.io needs these for file type detection + PDF rendering
    libmagic1 \
    poppler-utils \
    # Tesseract OCR for scanned PDFs
    tesseract-ocr \
    tesseract-ocr-eng \
    # OpenCV dependency (unstructured uses it for layout analysis)
    libgl1 \
    # Security: gosu lets us drop root privileges before running the app
    gosu \
    # Health checks + networking
    curl \
    netcat-openbsd \
    # Build tools (some Python packages need C compilation)
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Create non-root user ──
# Running as root inside containers is a security risk.
# If someone exploits a vulnerability, they get root access to the container.
# With appuser, they only get unprivileged access.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# ── Install Python dependencies ──
# Copy only pyproject.toml first. Docker caches this layer, so dependencies
# are only reinstalled when pyproject.toml changes — not on every code change.
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# ── Download NLP models that unstructured needs ──
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger')"

# ── Create directories for uploads and logs ──
RUN mkdir -p /app/storage/uploads /app/logs \
    && chown -R appuser:appuser /app/storage /app/logs

# ── Copy application code ──
# This layer changes frequently, so it's LAST (maximizes cache hits)
COPY . .

# ── Make scripts executable ──
RUN chmod +x /app/docker/scripts/*.sh

# ── Entrypoint handles permission fixing + drops to appuser ──
ENTRYPOINT ["/app/docker/scripts/entrypoint.sh"]

# ── Default command (overridden by docker-compose) ──
CMD ["bash", "/app/docker/scripts/start-api.sh"]