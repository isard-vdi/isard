FROM cypress/browsers
WORKDIR /usr/local/src/isard-frontend
ENV CYPRESS_CACHE_FOLDER /usr/local/src/isard-frontend/node_modules/.cache/cypress
CMD yarn test:e2e --headless
COPY frontend /usr/local/src/isard-frontend
RUN yarn install
