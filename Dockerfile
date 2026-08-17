# syntax=docker/dockerfile:1.9
#
# Layers are ordered strictly by how often they change, least-frequent first.
# During the exercise this image is rebuilt many times, so the only layer that
# should ever be invalidated by editing a .py file is the last one.
#
#   base image  ->  uv binary  ->  dependency manifest  ->  third-party deps
#                -> application source -> project install
#
# Two details do the heavy lifting:
#
#   * pyproject.toml and uv.lock are copied ON THEIR OWN, before the source.
#     Editing application code therefore never re-resolves or re-downloads a
#     dependency.
#   * The uv cache is a BuildKit cache mount, so even a genuine dependency
#     change reuses already-downloaded wheels instead of fetching them again.
#
# Base images are referenced by tag here and pinned to digests by
# scripts/pin_base_images.sh during bootstrap. A digest pin stops an upstream
# retag from silently busting the whole cache mid-session; it is written by a
# script rather than by hand so the value is always real.

ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.5.11

# ---------------------------------------------------------------------------
# Stage 1: dependencies. Changes only when pyproject.toml or uv.lock change.
# ---------------------------------------------------------------------------
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependency manifest only. This is the cache boundary that matters.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application source. Everything above this line survives a code edit.
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime. No build tooling, no uv, no dev dependencies, no source
# tree beyond what is installed.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

WORKDIR /app

COPY --from=builder --link --chown=10001:10001 /app/.venv /app/.venv
COPY --from=builder --link --chown=10001:10001 /app/src /app/src

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DUVO_SECRETS_DIR=/run/secrets \
    DUVO_LOG_FORMAT=json

USER 10001:10001

# Readiness, not liveness: this asks whether the container should receive
# traffic. See src/duvo_fde/health.py for why the two are kept apart.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-m", "duvo_fde", "health"]

ENTRYPOINT ["python", "-m", "duvo_fde"]
CMD ["serve"]

# ---------------------------------------------------------------------------
# Stage 3: the mock upstream used by docker compose and the smoke test.
# It needs fastapi and uvicorn, which the production image deliberately does
# not carry. Built from the same dependency layers, so it costs almost nothing.
# ---------------------------------------------------------------------------
FROM builder AS mock-builder
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra mock

FROM ${PYTHON_IMAGE} AS mock

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

WORKDIR /app
COPY --from=mock-builder --link --chown=10001:10001 /app/.venv /app/.venv
COPY --from=mock-builder --link --chown=10001:10001 /app/src /app/src

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["uvicorn", "duvo_fde.testing.mock_upstream:app", "--host", "0.0.0.0", "--port", "8080"]
