FROM node:alpine as frontend

RUN mkdir /isard-frontend
COPY frontend /isard-frontend

WORKDIR /isard-frontend

RUN yarn
RUN yarn build

RUN rm -rf src
RUN rm -rf node_modules
RUN rm -rf build

FROM nginx:alpine as production

COPY docker/static/default.conf /etc/nginx/conf.d/default.conf
COPY docker/static/spice-web-client /usr/share/nginx/html/viewer/spice-web-client
COPY docker/static/noVNC /usr/share/nginx/html/viewer/noVNC
COPY --from=frontend /isard-frontend/dist /usr/share/nginx/html