#
# old frontend
#
FROM oven/bun:1.4.4-alpine@sha256:4cf82f5686b196504fe119db3fcd9185b191f82ece82c40680e597228ec6070a AS old-frontend

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

RUN bun install --frozen-lockfile

WORKDIR /

COPY old-frontend /build

WORKDIR /build

RUN bun run build

#
# frontend
#
FROM oven/bun:1.4.4-alpine@sha256:4cf82f5686b196504fe119db3fcd9185b191f82ece82c40680e597228ec6070a AS frontend

ARG SRC_VERSION_ID
ENV SRC_VERSION_ID=$SRC_VERSION_ID

WORKDIR /build

COPY component/frontend/package.json /build
COPY component/frontend/bun.lock* /build
COPY component/frontend/.npmrc /build

RUN bun install --frozen-lockfile

WORKDIR /

COPY component/frontend /build

WORKDIR /build

# Generated API clients (src/gen/oas/) are tracked in git and copied
# via COPY above. If codegen runs in CI, the codegen job
# produces fresh files that override these committed versions.

# TODO: Run the typecheck here too!
RUN bun run build-only

#
# spice-ts
#
FROM oven/bun:1.4.4-alpine@sha256:4cf82f5686b196504fe119db3fcd9185b191f82ece82c40680e597228ec6070a AS spice-ts

WORKDIR /build

COPY docker/static/spice-ts/package.json /build
COPY docker/static/spice-ts/bun.lockb /build

RUN bun install --frozen-lockfile

WORKDIR /

COPY docker/static/spice-ts /build

WORKDIR /build

RUN bun run build

#
# nginx
#
FROM nginxinc/nginx-unprivileged:1.31.2-alpine-slim@sha256:eed3e4c2f3f9285e80610238e0b18fe1bf311c50559434db1969b1cfabd5518b as production

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
