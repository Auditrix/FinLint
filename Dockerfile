# FinLint as one container: the API and the website on one port.
#
#   docker compose up --build        then open http://localhost:8000
#
# Two stages. The first builds the website into plain files with Node. The
# second is Python only, and copies those files in, so Node never ships.

# --- stage 1: the website ----------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# Empty on purpose: the page and the API share one origin in this container,
# so every call goes to /api on the same host.
ENV NEXT_PUBLIC_API_BASE="" NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- stage 2: the engine and the API -----------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf
WORKDIR /app

# The CPU build of torch first. The default one bundles GPU libraries, several
# gigabytes this container would never use (Section 5: no GPU in hosting).
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && rm -rf build src/*.egg-info

# The embedding model is downloaded once, here, so the container starts
# without the internet and the first search is not a download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY docs/evaluation.json docs/evaluation.json
COPY --from=web /web/out web/out

# Never run as root. The uploads folder is the only place it writes.
RUN useradd --create-home --uid 1000 finlint \
    && mkdir -p data/uploads \
    && chown -R finlint data
USER finlint

ENV FINLINT_UPLOADS=/app/data/uploads \
    FINLINT_WEB=/app/web/out \
    FINLINT_EVALUATION=/app/docs/evaluation.json \
    HF_HUB_OFFLINE=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

CMD ["uvicorn", "finlint.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
