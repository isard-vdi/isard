FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev libvirt-dev musl-dev openssl-dev pciutils-dev pkgconfig

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --group test --package isardvdi-engine --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache curl libffi libvirt-client libvirt-libs openssh-client openssl pciutils sshpass

COPY --from=builder /.venv /.venv
COPY engine/engine /isard
COPY engine/docker/genrsa.sh /
COPY engine/docker/run.sh /
COPY engine/docker/add-hypervisor.sh /
ENV PATH="/.venv/bin:$PATH"
WORKDIR /isard
CMD ["/run.sh"]
