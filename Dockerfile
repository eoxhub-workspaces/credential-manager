FROM python:3.13-slim AS builder

WORKDIR /srv/service

# Install build dependencies for C-extensions (needed for cryptography/cffi)
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry and the Export plugin inside the builder
RUN pip install --no-cache-dir poetry poetry-plugin-export

# Copy only the files needed for dependency resolution
COPY pyproject.toml poetry.lock ./

# Install EVERYTHING (including dev tools) into the builder stage
# This makes the builder stage ready for pytest, flake8, and mypy
RUN poetry config virtualenvs.create false \
    && poetry install --with dev --no-interaction --no-ansi

# Export to requirements.txt
RUN poetry export -f requirements.txt --output requirements.txt --without dev

COPY my_credentials ./my_credentials

FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROMETHEUS_MULTIPROC_DIR=/var/tmp/prometheus_multiproc_dir

# Setup prometheus directory and install tini
RUN mkdir -p $PROMETHEUS_MULTIPROC_DIR \
    && chown www-data $PROMETHEUS_MULTIPROC_DIR \
    && chmod g+w $PROMETHEUS_MULTIPROC_DIR \
    && apt-get update && apt-get install -y tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/service

# Copy ONLY the requirements file from the builder stage
COPY --from=builder /srv/service/requirements.txt .

# Install the production-ready requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY my_credentials ./my_credentials
COPY templates ./templates
COPY gunicorn.conf.py .

# Use tini as the entrypoint to handle signal forwarding
ENTRYPOINT ["/usr/bin/tini", "--"]

USER www-data

CMD ["gunicorn", "--bind=0.0.0.0:8080", "--config", "gunicorn.conf.py", "--workers=1", "-k", "uvicorn.workers.UvicornWorker", "--log-level=INFO", "my_credentials:app"]