FROM alpine:3.20

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip yarn

COPY webapp/docker/requirements.txt .
RUN pip install -r requirements.txt --break-system-package && \
    rm requirements.txt

# Copy the isard source
COPY webapp/webapp /isard

RUN cd /isard/webapp && yarn install
COPY component/_common/src /isard/webapp/_common
EXPOSE 5000
COPY webapp/docker/healthcheck.js /
HEALTHCHECK --interval=12s --timeout=12s --start-period=30s \
    CMD node /healthcheck.js
WORKDIR /isard
CMD [ "python3", "-u", "start.py" ]
STOPSIGNAL SIGINT
USER nobody