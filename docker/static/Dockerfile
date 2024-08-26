#
# old frontend
#
FROM node:18.20-alpine AS old-frontend

RUN mkdir /isard-frontend
COPY old-frontend /isard-frontend

ARG SRC_VERSION_ID
ARG SRC_VERSION_LINK

WORKDIR /isard-frontend

RUN apk add python3 make g++
RUN yarn install --frozen-lockfile
RUN yarn build

RUN rm -rf src
RUN rm -rf node_modules
RUN rm -rf build

#
# frontend
#
FROM oven/bun:1.1.24-alpine AS frontend

WORKDIR /build

COPY frontend/package.json /build
COPY frontend/bun.lockb /build

RUN bun install --frozen-lockfile

WORKDIR /

COPY frontend /build

WORKDIR /build

# TODO: Run the typecheck here too!
RUN bun run build-only

#
# spice-ts
#
FROM oven/bun:1.1.24-alpine AS spice-ts

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
FROM nginxinc/nginx-unprivileged:1.27-alpine-slim as production

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
COPY old-frontend/src/assets/logo.svg /usr/share/nginx/html/old-frontend/default_logo.svg
COPY --from=old-frontend /isard-frontend/dist /usr/share/nginx/html/old-frontend
