# The production image: the API serving the built client, one origin.
#
#   docker build --build-arg CATALOG_URL=... -t usched .
#   docker run -p 8000:8000 --env-file .env usched
#
# The catalog database is not in the repo: pass the CATALOG_URL that
# `npm run catalog -- publish` prints. README "Deploying" walks through it.

FROM node:26-slim AS client
WORKDIR /app
# The client is an npm workspace; --ignore-scripts skips the root
# postinstall, which syncs Python and belongs to the next stage.
COPY package.json package-lock.json ./
COPY client/package.json client/
RUN npm ci --ignore-scripts
COPY client/ client/
RUN npm run build -w client

FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
# Runtime dependencies only: no dev tools, no browser for fetching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY server/ server/
COPY --from=client /app/client/dist client/dist
ARG CATALOG_URL
RUN test -n "$CATALOG_URL" || \
  (echo "Set CATALOG_URL (npm run catalog -- publish prints it)" && exit 1)
ADD ${CATALOG_URL} server/data/catalog.db

# Hosts such as Render set PORT; 8000 otherwise.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port ${PORT}"]
