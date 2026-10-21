FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache .

# The chunking tokenizer's encoding file is fetched here, at build time, so
# the worker never downloads it at runtime (ADR-0011).
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY release.sh ./

ENV PYTHONPATH=/app/app

# The commit SHA the image is built from, so Sentry events carry the release.
ARG GIT_SHA
ENV SENTRY_RELEASE=${GIT_SHA}

# Workers and graceful timeout come from env. The graceful timeout lets
# in-flight Ask streams finish when a deploy stops the container. `exec` so
# gunicorn, not sh, receives the stop signal.
CMD ["sh", "-c", "exec gunicorn -k uvicorn_worker.UvicornWorker main:app --bind 0.0.0.0:8000 --workers \"${GUNICORN_WORKERS:-2}\" --graceful-timeout \"${GUNICORN_GRACEFUL_TIMEOUT:-30}\""]
