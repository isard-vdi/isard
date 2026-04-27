FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev libvirt-dev musl-dev openssl-dev pciutils-dev pkgconfig

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --group test --package isardvdi-engine --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache curl libffi libvirt-client libvirt-libs openssh-client openssl pciutils sshpass

COPY --from=builder /workspace/.venv /.venv
COPY engine/engine /isard
COPY engine/docker/genrsa.sh /
COPY engine/docker/run.sh /
COPY engine/docker/add-hypervisor.sh /
ENV PATH="/.venv/bin:$PATH"
WORKDIR /isard
CMD ["/run.sh"]
