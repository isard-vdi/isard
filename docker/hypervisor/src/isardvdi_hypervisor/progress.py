import os
import time
import traceback

from isardvdi_apiv4_client.api.role_admin import admin_hypervisor_boot_progress
from isardvdi_apiv4_client.models import (
    AdminBootProgressRequest,
    AdminBootProgressRequestBootProgress,
)
from isardvdi_apiv4_client_auth import build_client, raise_for_status


def report_progress(step, total, label, error=None):
    """Report boot progress step to the API (fire-and-forget).

    Sends the structured ``{step, total, label, error, timestamp}``
    object directly (the endpoint accepts a JSON object; RethinkDB
    stores it verbatim for the changefeed to fan out).
    """
    try:
        hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
        with build_client("isard-hypervisor", role="hypervisor") as client:
            payload = AdminBootProgressRequestBootProgress.from_dict(
                {
                    "step": step,
                    "total": total,
                    "label": label,
                    "error": error,
                    "timestamp": int(time.time()),
                }
            )
            resp = admin_hypervisor_boot_progress.sync_detailed(
                hyper_id=hyper_id,
                client=client,
                body=AdminBootProgressRequest(boot_progress=payload),
            )
            raise_for_status(resp)
    except Exception:
        traceback.print_exc()
