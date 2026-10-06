# The API image. Two stages: the first resolves nothing (uv installs exactly what uv.lock
# records) and builds the package; the second carries only the virtual environment, so
# neither uv nor the source tree ships in the image that runs.
#
# Base images are pinned by digest, the image equivalent of SUPPLY-CHAIN-SECURITY.md
# rule 4 (a tag can be moved to other content, a digest cannot). The Python tag matches
# backend/.python-version and the uv tag matches the version CI installs.
FROM python:3.14.7-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.8@sha256:d1cbaeadc234fe19c0d93daabcf5e98738cd93c6d1dd4918ef6aa30735feb23a /uv /usr/local/bin/uv

# The environment lives outside the source tree so the runtime stage can copy it alone.
# Python downloads are off: the image's interpreter is the pinned one, and a silent
# download would mean the lockfile and the interpreter had drifted apart.
ENV UV_PROJECT_ENVIRONMENT=/opt/influence \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /build

# Dependencies first, in their own layer: a change under src/ does not reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# Then the package itself, installed as a wheel (not editable) so it needs no source tree.
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14.7-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56

# An unprivileged user: the API only reads the law bundles under /data.
RUN useradd --create-home --uid 1000 influence

COPY --from=builder /opt/influence /opt/influence

# /data is where `influence atlas` and `influence lineage` write; compose mounts the
# repository's data/ (or mock-data/) there. The default is explicit because the
# installed package's "beside the source" fallback has no meaning inside an image.
ENV PATH=/opt/influence/bin:$PATH \
    INFLUENCE_DATA_ROOT=/data \
    PYTHONUNBUFFERED=1

USER influence
WORKDIR /home/influence
EXPOSE 8000

# The same /health the explorer and `make check-containers` read; slim images have no curl.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "influence.api:app", "--host", "0.0.0.0", "--port", "8000"]
