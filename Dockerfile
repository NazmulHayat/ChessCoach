# elo101 web app (server version): FastAPI + Stockfish 18 + the built React frontend, one image.
#   docker build -t chesscoach .
#   docker run -p 8000:8000 -e CHESSCOACH_WORKERS=2 chesscoach

# ---- Stockfish 18, compiled for the target CPU (x86-64 AVX2 by default, armv8 on ARM) ----
FROM debian:bookworm-slim AS stockfish
ARG TARGETARCH
ARG SF_ARCH=""
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch sf_18 https://github.com/official-stockfish/Stockfish.git /sf
WORKDIR /sf/src
RUN arch="${SF_ARCH:-$([ "$TARGETARCH" = "arm64" ] && echo armv8 || echo x86-64-avx2)}" \
    && make -j"$(nproc)" profile-build ARCH="$arch" COMP=gcc \
    && strip stockfish && ./stockfish quit

# ---- frontend ----
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY --from=stockfish /sf/src/stockfish /usr/local/bin/stockfish
COPY ep_model/ ep_model/
COPY --from=web /web/dist web/dist

# Tunables (see ep_model/review/server.py): engine depth and processes, request limits.
ENV CHESSCOACH_DEPTH=17 \
    CHESSCOACH_WORKERS=2 \
    CHESSCOACH_MAX_CONCURRENT=2 \
    CHESSCOACH_REVIEWS_PER_HOUR=30 \
    CHESSCOACH_MAX_PLIES=400 \
    PORT=8000 \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"
CMD ["sh", "-c", "python -m ep_model.review.server --host 0.0.0.0 --port ${PORT}"]
