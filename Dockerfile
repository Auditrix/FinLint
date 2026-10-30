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
    PIP_RETRIES=10 \
    PIP_TIMEOUT=60 \
    HF_HOME=/opt/hf
WORKDIR /app

# The CPU build of torch first. The default one bundles GPU libraries, several
# gigabytes this container would never use (Section 5: no GPU in hosting).
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Every dependency, in its own layer, BEFORE any of our code is copied. Docker
# reuses a layer until something it copied changes, so an edit to src/ never
# downloads these again. With the code copied first, every small change meant
# 155 fresh downloads, and one dropped connection threw the whole attempt away.
# An empty package stands in for ours, because pyproject.toml needs one to build.
# The cache keeps finished downloads between attempts, then is deleted.
COPY pyproject.toml ./
RUN mkdir -p src/finlint && touch src/finlint/__init__.py README.md \
    && for attempt in 1 2 3 4 5; do \
         env -u PIP_NO_CACHE_DIR pip install --cache-dir /tmp/pip-cache . && break; \
         [ "$attempt" = 5 ] && exit 1; \
         echo "pip attempt $attempt failed, trying again"; sleep 10; \
       done \
    && rm -rf /tmp/pip-cache build src README.md

# The embedding model is downloaded once, here, so the container starts
# without the internet and the first search is not a download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

# Our own code last. It is not installed, only copied, and Python finds it
# through PYTHONPATH. "pip install ." here looked harmless but downloads
# setuptools and wheel first, so a dropped connection failed the build at the
# very last step. This way the code step needs no internet at all.
RUN pip uninstall --yes finlint
COPY src ./src
ENV PYTHONPATH=/app/src

COPY docs/evaluation.json docs/evaluation.json
COPY scripts/create_user.py scripts/create_user.py
COPY --from=web /web/out web/out

# Never run as root. The uploads folder is the only place it writes.
RUN useradd --create-home --uid 1000 finlint \
    && mkdir -p data/uploads \
    && chown -R finlint data
USER finlint

# FINLINT_CORS_ORIGINS is empty: the page and the API share this origin, so no
# other site is allowed to call the API with someone's session cookie.
ENV FINLINT_UPLOADS=/app/data/uploads \
    FINLINT_WEB=/app/web/out \
    FINLINT_EVALUATION=/app/docs/evaluation.json \
    FINLINT_CORS_ORIGINS="" \
    HF_HUB_OFFLINE=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

# --no-proxy-headers: the rate limits key on the caller's address, and an
# X-Forwarded-For header is just text anyone can send. Behind a real proxy,
# replace it with --forwarded-allow-ips <that proxy's address>, or every user
# shares the proxy's address and therefore one set of limits.
CMD ["uvicorn", "finlint.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
