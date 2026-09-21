FROM ghcr.io/astral-sh/uv:0.11.7-python3.13-trixie AS uv

# -----------------------------------
# STAGE 1: prod stage
# Only install main dependencies
# -----------------------------------
FROM python:3.13-slim-trixie AS prod
RUN apt-get update && apt-get install -y \
  gcc \
  && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_NO_MANAGED_PYTHON=1
# Required by prometheus-client to share metrics between [uvi|guni]corn
# workers. Baked into the image so it's ready before the app starts --
# lower- and uppercase because different prometheus-client versions read
# different casing.
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-metrics
ENV prometheus_multiproc_dir=/tmp/prometheus-metrics
RUN mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

WORKDIR /app/src

RUN --mount=from=uv,source=/usr/local/bin/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . .

RUN --mount=from=uv,source=/usr/local/bin/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------
# STAGE 3: development build
# Includes dev dependencies
# -----------------------------------
FROM prod AS dev

RUN --mount=from=uv,source=/usr/local/bin/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-groups
