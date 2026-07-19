#
# old frontend
#
FROM oven/bun:1.3-alpine AS old-frontend

ARG SRC_VERSION_ID
ARG SRC_VERSION_LINK

RUN apk add --no-cache \
    python3 \
    make \
    g++

WORKDIR /build

COPY old-frontend/package.json /build
COPY old-frontend/bun.lock /build
COPY old-frontend/.npmrc /build

RUN for i in 1 2 3; do \
      bun install --frozen-lockfile --network-concurrency 8 && break; \
      echo "bun install failed (attempt $i) - clearing partial state, retrying"; \
      rm -rf node_modules /root/.bun/install/cache; sleep 3; \
    done

WORKDIR /

COPY old-frontend /build

WORKDIR /build

RUN bun run build

#
# frontend
#
FROM oven/bun:1.3-alpine AS frontend

ARG SRC_VERSION_ID
ENV SRC_VERSION_ID=$SRC_VERSION_ID

WORKDIR /build

COPY component/frontend/package.json /build
COPY component/frontend/bun.lock* /build

RUN for i in 1 2 3; do \
      bun install --frozen-lockfile --network-concurrency 8 && break; \
      echo "bun install failed (attempt $i) - clearing partial state, retrying"; \
      rm -rf node_modules /root/.bun/install/cache; sleep 3; \
    done

WORKDIR /

COPY component/frontend /build

WORKDIR /build

# Generated API clients (src/gen/oas/) are tracked in git and copied
# via COPY above. If codegen runs in CI, the gen-protobuf stage
# produces fresh files that override these committed versions.

# TODO: Run the typecheck here too!
RUN bun run build-only

#
# spice-ts
#
FROM oven/bun:1.3-alpine AS spice-ts

WORKDIR /build

COPY docker/static/spice-ts/package.json /build
COPY docker/static/spice-ts/bun.lockb /build

RUN for i in 1 2 3; do \
      bun install --frozen-lockfile --network-concurrency 8 && break; \
      echo "bun install failed (attempt $i) - clearing partial state, retrying"; \
      rm -rf node_modules /root/.bun/install/cache; sleep 3; \
    done

WORKDIR /

COPY docker/static/spice-ts /build

WORKDIR /build

RUN bun run build

#
# nginx
#
FROM nginxinc/nginx-unprivileged:1.27.4-alpine-slim as production

USER root
RUN apk -U upgrade --no-cache
USER 101

# Nginx configuration
COPY docker/static/default.conf /etc/nginx/conf.d/default.conf

# Viewers
COPY docker/static/noVNC /usr/share/nginx/html/viewer/noVNC
COPY --from=spice-ts /build/dist /usr/share/nginx/html/viewer/spice-ts

# Frontend
COPY --from=frontend /build/dist /usr/share/nginx/html/frontend

# Old frontend
COPY --from=old-frontend /build/dist /usr/share/nginx/html/old-frontend
