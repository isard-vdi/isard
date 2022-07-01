FROM cypress/browsers:node14.19.0-chrome100-ff99-edge
WORKDIR /usr/local/src/isard-frontend
ENV CYPRESS_CACHE_FOLDER /usr/local/src/isard-frontend/node_modules/.cache/cypress
CMD yarn test:e2e --headless
COPY frontend /usr/local/src/isard-frontend
RUN yarn install
