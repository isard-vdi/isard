# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

"""Pin the start_domain failure paths' clearance of stale vgpu_info.

Without this clearance, GPU desktops that hit a worker-side start failure (e.g.
libvirt "mediated device <UUID> not found" after a hypervisor reboot) end up
Failed with vgpu_info still pointing to the orphan mdev UUID; the balancer's
reactive requeue then loops Failed -> Starting -> Failed forever, never going
through start_domain_from_id, so the cleanup never runs. Mirrors origin/main
``26885eff7``.
"""

from unittest.mock import MagicMock, patch

from engine.services.threads.hyp_worker_thread import HypWorkerThread


def _build_worker():
    """Return a minimal HypWorkerThread proxy for invoking individual handler
    methods. We bypass __init__ on purpose — the production constructor
    spins libvirt connections, queues, threads. The handlers we exercise
    only read self.hyp_id / self.stop / a couple of helpers; we set them
    directly."""
    w = HypWorkerThread.__new__(HypWorkerThread)
    w.hyp_id = "hyp-test"
    w.stop = False
    w._cleanup_queued_actions = MagicMock()
    return w


def _action():
    return {
        "id_domain": "_admin_dsk-1",
        "type": "start_domain",
        "nvidia_uid": False,
    }


@patch("engine.services.threads.hyp_worker_thread.update_vgpu_info_if_stopped")
@patch("engine.services.threads.hyp_worker_thread.log_action")
@patch("engine.services.threads.hyp_worker_thread.update_domain_status")
def test_libvirt_error_clears_vgpu_info_on_generic_failure(
    mock_update_status, mock_log_action, mock_update_vgpu
):
    """The else branch of _handle_libvirt_error_in_start_domain (real failure,
    not the "already exists" or LibvirtTimeoutError fast-paths) must clear
    stale vgpu_info so the next retry can reallocate."""
    w = _build_worker()
    err = RuntimeError("mediated device 1234-5678 not found")
    action = _action()
    w._handle_libvirt_error_in_start_domain(err, action, 0.0, [])

    mock_update_vgpu.assert_called_once_with(action["id_domain"])


@patch("engine.services.threads.hyp_worker_thread.update_vgpu_info_if_stopped")
@patch("engine.services.threads.hyp_worker_thread.log_action")
@patch("engine.services.threads.hyp_worker_thread.update_domain_status")
def test_libvirt_error_skips_vgpu_clear_on_already_exists_path(
    mock_update_status, mock_log_action, mock_update_vgpu
):
    """The "already exists with uuid" branch flips status to Started, NOT
    Failed. The vgpu_info clearance is only relevant on the Failed branch —
    this path must not touch it."""
    w = _build_worker()
    err = RuntimeError("Domain already exists with uuid 1111")
    w._handle_libvirt_error_in_start_domain(err, _action(), 0.0, [])

    mock_update_vgpu.assert_not_called()


@patch("engine.services.threads.hyp_worker_thread.update_vgpu_info_if_stopped")
@patch("engine.services.threads.hyp_worker_thread.log_action")
@patch("engine.services.threads.hyp_worker_thread.update_domain_status")
@patch("engine.services.threads.hyp_worker_thread.update_vgpu_uuid_domain_action")
def test_generic_error_clears_vgpu_info(
    mock_update_uuid, mock_update_status, mock_log_action, mock_update_vgpu
):
    """_handle_generic_error_in_start_domain catches non-libvirt exceptions
    raised mid-start (e.g. paramiko, network glue). It must also clear stale
    vgpu_info so a non-GPU desktop's no-op + a GPU desktop's real reset both
    converge on a clean retry."""
    w = _build_worker()
    err = RuntimeError("ssh exception")
    action = _action()
    w._handle_generic_error_in_start_domain(err, action, 0.0, [])

    mock_update_vgpu.assert_called_once_with(action["id_domain"])
