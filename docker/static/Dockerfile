#
# frontend
#
FROM node:18.20-alpine as frontend

RUN mkdir /isard-frontend
COPY frontend /isard-frontend

ARG SRC_VERSION_ID
ARG SRC_VERSION_LINK
RUN sed -i "s*isard_display_version*${SRC_VERSION_ID}*g" /isard-frontend/src/views/Login.vue
RUN sed -i "s,isard_changelog_link,${SRC_VERSION_LINK},g"  /isard-frontend/src/views/Login.vue

WORKDIR /isard-frontend

RUN apk add python3 make g++
RUN yarn
RUN yarn build

RUN rm -rf src
RUN rm -rf node_modules
RUN rm -rf build

#
# spice-ts
#
FROM oven/bun:1.1.18 as spice-ts

WORKDIR /build

COPY docker/static/spice-ts/package.json /build
COPY docker/static/spice-ts/bun.lockb /build

RUN bun install

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
COPY frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg
COPY --from=frontend /isard-frontend/dist /usr/share/nginx/html
