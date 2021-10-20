FROM node:alpine as frontend

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

FROM nginx:alpine as production

COPY docker/static/default.conf /etc/nginx/conf.d/default.conf
COPY docker/static/spice-web-client /usr/share/nginx/html/viewer/spice-web-client
COPY docker/static/noVNC /usr/share/nginx/html/viewer/noVNC
COPY frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg
COPY --from=frontend /isard-frontend/dist /usr/share/nginx/html
