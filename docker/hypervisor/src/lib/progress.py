import json
import os
import time
import traceback

from api_client import ApiClient


def report_progress(step, total, label, error=None):
    """Report boot progress step to the API (fire-and-forget)."""
    try:
        hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
        apic = ApiClient()
        apic.update(
            "hypervisor/" + hyper_id + "/boot_progress",
            data={
                "boot_progress": json.dumps(
                    {
                        "step": step,
                        "total": total,
                        "label": label,
                        "error": error,
                        "timestamp": int(time.time()),
                    }
                )
            },
        )
    except Exception:
        traceback.print_exc()
