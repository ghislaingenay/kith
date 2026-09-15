FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

ENV PYTHONPATH=/app/app

CMD ["gunicorn", "-k", "uvicorn_worker.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]
