FROM fedora:44@sha256:6c75d5bf57cb0fa5aa4b92c6a83c86c791644496d9ac230de7711f5b8ec3b898 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs (#!/.venv/bin/python) keep resolving
# after COPY --from=builder /.venv /.venv.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/.venv

RUN dnf install -y autoconf automake gcc gettext-devel git libffi-devel libtool openssl-devel pkg-config python3-devel && dnf clean all

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-storage --no-editable

FROM fedora:44@sha256:6c75d5bf57cb0fa5aa4b92c6a83c86c791644496d9ac230de7711f5b8ec3b898 AS runtime
RUN dnf install -y libguestfs libguestfs-tools-c libvirt-client libvirt-daemon libvirt-daemon-config-network openssl-libs python3-cachetools python3-libguestfs python3-libvirt rsync virt-install virt-v2v virt-win-reg && dnf clean all

ENV LIBGUESTFS_BACKEND=direct
RUN useradd -ms /bin/bash v2v

COPY --from=builder /.venv /.venv
COPY docker/storage/task /opt/isardvdi/isardvdi_task
COPY docker/storage/init.sh /init.sh
RUN mkdir /utils
COPY docker/storage/utils /utils
ENV PATH="/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/utils"
CMD ["/init.sh"]
