# The production image: the API serving the built client, one origin.
#
#   docker build -t usched .
#   docker run -p 8000:8000 -e GEMINI_API_KEY=... usched
#
# The catalog database is not in the repo; the build downloads the copy
# `npm run publish:catalog` uploaded to this repo's "catalog" release.
# README "Deploying" walks through the whole flow.

FROM node:26-slim AS client
WORKDIR /app/client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
# Runtime dependencies only: no dev tools, no browser for fetching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY server/ server/
COPY --from=client /app/client/dist client/dist
ARG CATALOG_URL=https://github.com/arvinduh/usched/releases/download/catalog/catalog.db
ADD ${CATALOG_URL} server/data/catalog.db

# Hosts such as Render set PORT; 8000 otherwise.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port ${PORT}"]
