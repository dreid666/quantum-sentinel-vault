# syntax=docker/dockerfile:1

# ==============================================================================
# Stage 1: Hardened Express API (default runtime target)
# ==============================================================================
FROM node:20-alpine AS api

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY api/ ./api/

USER node
ENV NODE_ENV=production \
    PORT=3000
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

CMD ["node", "api/server.js"]

# ==============================================================================
# Stage 2: Sentinel + Foundry + Slither + Quantum ML Environment
# ==============================================================================
FROM ghcr.io/foundry-rs/foundry:latest AS foundry-bins

FROM python:3.11-slim AS sentinel

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Foundry toolchain binaries (forge, cast, anvil, chisel)
COPY --from=foundry-bins /usr/local/bin/forge /usr/local/bin/forge
COPY --from=foundry-bins /usr/local/bin/cast /usr/local/bin/cast
COPY --from=foundry-bins /usr/local/bin/anvil /usr/local/bin/anvil
COPY --from=foundry-bins /usr/local/bin/chisel /usr/local/bin/chisel

WORKDIR /workspace

COPY requirements.txt ./
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt \
    slither-analyzer==0.11.6 \
    solc-select \
    && solc-select install 0.8.20 \
    && solc-select use 0.8.20

COPY . .

CMD ["python3", "agent_core/edge_sentinel.py", "src/Vault.sol"]
