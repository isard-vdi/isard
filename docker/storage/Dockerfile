# syntax=docker/dockerfile:1.20

FROM fedora:44@sha256:15da97ed9aa94dd3d92c3925eb89520f6c80e07ea7ee24cba848d1f8b6912b3e AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs (#!/.venv/bin/python) keep resolving
# after COPY --from=builder /.venv /.venv.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/.venv

RUN dnf install -y autoconf automake gcc gettext-devel git libffi-devel libtool openssl-devel pkg-config python3-devel && dnf clean all

WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-storage --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-storage --no-editable

FROM fedora:44@sha256:15da97ed9aa94dd3d92c3925eb89520f6c80e07ea7ee24cba848d1f8b6912b3e AS runtime
RUN dnf install -y libguestfs libguestfs-tools-c libvirt-client libvirt-daemon libvirt-daemon-config-network openssl-libs python3-cachetools python3-libguestfs python3-libvirt rsync virt-install virt-v2v virt-win-reg && dnf clean all

ENV LIBGUESTFS_BACKEND=direct
RUN useradd -ms /bin/bash v2v

COPY --from=builder /.venv /.venv
COPY docker/storage/init.sh /init.sh
RUN mkdir /utils
COPY docker/storage/utils /utils
ENV PATH="/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/utils"
CMD ["/init.sh"]
