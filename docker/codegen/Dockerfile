FROM golang:1.25.8-alpine3.22

# Force Go's resolver to use IPv4-only DNS so module downloads
# work on hosts where IPv6 egress to proxy.golang.org is broken.
ENV GODEBUG=netdns=go+4

RUN apk -U upgrade --no-cache
# grpc-plugins ships grpc_python_plugin so buf.gen.yaml can call it locally
# instead of fetching buf.build/grpc/python over the network on every codegen
# (avoids resource_exhausted / deadline_exceeded rate-limit failures).
# git is required by pip to fetch the isard-vdi/rethinkdb-python fork
# from /apiv4_requirements.txt (``git+https://...``).
RUN apk add --no-cache git python3 npm protoc grpc-plugins

RUN go install github.com/bufbuild/buf/cmd/buf@v1.50.0 && \
  go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1 && \
  go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@v1.5.1 && \
  go install github.com/ogen-go/ogen/cmd/ogen@v1.4.1 && \
  go install github.com/vektra/mockery/v2@v2.53.6

RUN python3 -m venv /venv && \
  source /venv/bin/activate && \
  pip3 install \
  "betterproto[compiler]==2.0.0-beta6" \
  "grpcio-tools==1.66.2"


COPY component/apiv4/docker/requirements.txt /apiv4_requirements.txt
# RETHINKDB_FORK_SHA is the current branch HEAD of
# isard-vdi/rethinkdb-python @ modernize-python-client. CI resolves
# it once per pipeline (see ``resolve-rethinkdb-fork-sha`` in
# .gitlab-ci.yml) and passes it via ``--build-arg``. Embedding the
# SHA in the layer command makes Docker invalidate the apiv4-venv
# pip-install layer when the branch advances; without it the layer
# would stay cached on the first SHA seen and pip would never
# refetch.
ARG RETHINKDB_FORK_SHA=unknown
RUN echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" && \
  python3 -m venv /apiv4-venv && \
  source /apiv4-venv/bin/activate && \
  pip3 install --no-cache-dir -r /apiv4_requirements.txt && \
  pip3 install "pyyaml==6.0.2"

RUN npm install -g @bufbuild/protoc-gen-es@2.6.0 @bufbuild/protobuf@2.6.0 @bufbuild/protoplugin@2.6.0 @bufbuild/protoc-gen-es@2.6.0

WORKDIR /deps

# We need to install it 'locally', otherwise it won't work
RUN npm install \
  @hey-api/openapi-ts@0.92.4 \
  @asyncapi/cli@6.0.0 && \
  mkdir -p /deps/node_modules/@asyncapi/cli/lib/utils/logs

COPY component/_common/isardvdi_common /deps/py/isardvdi_common
ENV PYTHONPATH=/deps/py

COPY docker/codegen/gen.sh /gen.sh
COPY docker/codegen/changefeed_utils.py /changefeed_utils.py
COPY docker/codegen/gen_changefeed_asyncapi.py /gen_changefeed_asyncapi.py
COPY docker/codegen/gen_changefeed_subscribers.py /gen_changefeed_subscribers.py

WORKDIR /build

CMD [ "/gen.sh" ]
