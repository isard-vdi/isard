# syntax=docker/dockerfile:1.20

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev libvirt-dev musl-dev openssl-dev pciutils-dev pkgconfig

WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --group test --package isardvdi-engine --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --group test --package isardvdi-engine --no-editable

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS runtime
RUN apk add --no-cache curl libffi libvirt-client libvirt-libs openssh-client openssl pciutils sshpass

COPY --from=builder /.venv /.venv
COPY engine/src /isard
COPY engine/docker/genrsa.sh /
COPY engine/docker/run.sh /
COPY engine/docker/add-hypervisor.sh /
ENV PATH="/.venv/bin:$PATH"
WORKDIR /isard
CMD ["/run.sh"]
