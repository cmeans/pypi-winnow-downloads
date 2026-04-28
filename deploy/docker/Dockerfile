# Multi-stage Dockerfile for pypi-winnow-downloads.
#
# Build context expected at the repo root:
#   docker build -f deploy/docker/Dockerfile -t pypi-winnow-downloads:dev .
#
# Run as a one-shot (the collector exits after each daily run; host or
# orchestrator handles scheduling):
#   docker run --rm \
#     -v $PWD/config.yaml:/etc/pypi-winnow-downloads/config.yaml:ro \
#     -v $PWD/gcp.json:/etc/pypi-winnow-downloads/gcp.json:ro \
#     -v badge_output:/var/lib/pypi-winnow-downloads/output \
#     -e GOOGLE_APPLICATION_CREDENTIALS=/etc/pypi-winnow-downloads/gcp.json \
#     pypi-winnow-downloads:dev
#
# See compose.yml.example for a Docker Compose layout that pairs the
# collector with a Caddy static server sharing the output volume.

# --- build stage --------------------------------------------------------
FROM python:3.14-slim AS build

RUN pip install --no-cache-dir 'uv>=0.5,<1'

WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

# Build the package + runtime deps into a venv at a known absolute path.
# `--frozen` enforces uv.lock so a stale or missing lock fails the build
# loudly. `--no-dev` skips the dev extras (pytest, ruff, mypy).
# `--no-editable` is load-bearing: uv sync installs the project in
# editable mode by default, which writes a .pth file pointing at
# /src/src. That path does NOT exist in the runtime stage after
# `COPY --from=build /opt/venv /opt/venv`, so the venv ships a dangling
# import path and `import pypi_winnow_downloads` fails at startup.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-editable

# --- runtime stage ------------------------------------------------------
FROM python:3.14-slim AS runtime

# Non-root service account. The output directory is the only writable
# path the collector touches; config + credential live read-only under
# /etc/pypi-winnow-downloads/.
RUN useradd --system --shell /usr/sbin/nologin --home-dir /var/lib/pypi-winnow-downloads winnow \
    && install -d -o winnow -g winnow -m 0755 /var/lib/pypi-winnow-downloads/output \
    && install -d -o root   -g winnow -m 0750 /etc/pypi-winnow-downloads

# Copy the venv from the build stage. Path stays the same so shebangs
# inside the venv resolve.
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

USER winnow
WORKDIR /var/lib/pypi-winnow-downloads

# The container is a one-shot: it exits when the collector finishes.
# Schedule from the host (cron, systemd timer, k8s CronJob, etc.).
ENTRYPOINT ["winnow-collect", "--config", "/etc/pypi-winnow-downloads/config.yaml"]
