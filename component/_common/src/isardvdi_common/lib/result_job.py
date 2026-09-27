#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The storage workers' job class: a job's result event is committed with its outcome."""

from rq.job import Job

from ..helpers.task_streams import RESULT_STREAM, maxlen_for_stream


class ResultJob(Job):
    """Publishes ``kind=result`` in the transaction that writes the final status."""

    def _handle_success(self, result_ttl, pipeline, *args, **kwargs):
        super()._handle_success(result_ttl, pipeline, *args, **kwargs)
        self._publish_result(pipeline, "finished")

    def _handle_failure(self, exc_string, pipeline, *args, **kwargs):
        super()._handle_failure(exc_string, pipeline, *args, **kwargs)
        self._publish_result(pipeline, "failed")

    def _publish_result(self, pipeline, job_status):
        fields = {
            "kind": "result",
            "task_id": self.id,
            "task_name": self.func_name.rsplit(".", 1)[-1],
            "queue": self.origin,
            "job_status": job_status,
        }
        migration_id = (self.meta or {}).get("migration_id")
        if migration_id is not None:
            fields["migration_id"] = str(migration_id)
        pipeline.xadd(
            RESULT_STREAM,
            fields,
            maxlen=maxlen_for_stream(RESULT_STREAM),
            approximate=True,
        )
