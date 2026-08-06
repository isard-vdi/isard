# SPDX-License-Identifier: AGPL-3.0-or-later

"""The old-tasks sweep must never delete work that has not finished - and must
never be stopped from running by the config it was handed.

Three halves of the same nightly pass. The config surface accepted registries
the sweep then refused (so every nightly run raised and nothing was ever
purged), the age test counted a missing `ended_at` as "old" - which is exactly
what a DEFERRED or running job has - and, once both were guarded, a single
unusable entry in a stored config still aborted the whole pass before it
examined one job. The unattended path now skips what it cannot reap and says
so; the operator-facing setter still refuses outright.

The other end of that guard: in a terminal registry a job with no `ended_at`
is not live, it is unreachable. rq never sets one when a job is cancelled, nor
when `StartedJobRegistry` cleanup declares an abandoned job failed - so without
a fallback those entries can never be swept at all.
"""

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.services.admin.queues import NON_REAPABLE_REGISTRIES, AdminQueuesService

ALL_SEVEN = [
    "queued",
    "started",
    "finished",
    "failed",
    "deferred",
    "scheduled",
    "canceled",
]
REAPABLE = ["finished", "failed", "canceled"]


def _ago(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


class TestLiveRegistriesAreRefusedEverywhere:
    @pytest.mark.parametrize("registry", NON_REAPABLE_REGISTRIES)
    def test_sweep_refuses_them(self, registry):
        with pytest.raises(Exception) as exc:
            AdminQueuesService._get_old_jobs(3600, registries=[registry])
        assert registry in str(exc.value)

    @pytest.mark.parametrize("registry", NON_REAPABLE_REGISTRIES)
    def test_config_refuses_them_too(self, registry):
        """Accepting a registry the sweep rejects is what bricked the nightly
        run: valid to store, impossible to execute."""
        with pytest.raises(Exception) as exc:
            AdminQueuesService.set_queue_registries([registry])
        assert registry in str(exc.value)

    def test_deferred_is_among_them(self):
        assert "deferred" in NON_REAPABLE_REGISTRIES

    def test_reapable_registries_are_still_accepted(self):
        with patch(
            "api.services.admin.queues.Config.update_old_tasks", return_value=None
        ):
            out = AdminQueuesService.set_queue_registries(["finished", "failed"])
        assert out == {"queue_registries": ["finished", "failed"]}


class TestTheNightlySweepDegradesInsteadOfDying:
    """A stored config the sweep cannot execute must cost the entries it names,
    not the entire pass."""

    def _run_auto(self, registries):
        config = {
            "enabled": True,
            "older_than": 1209600,
            "queue_registries": registries,
        }
        with (
            patch.object(
                AdminQueuesService, "get_auto_delete_config", return_value=config
            ),
            patch.object(
                AdminQueuesService, "_get_old_jobs", return_value=[]
            ) as get_old_jobs,
            patch.object(AdminQueuesService, "_delete_jobs", return_value=([], [])),
            patch(
                "api.services.admin.queues.clear_queue_data_caches", return_value=None
            ),
        ):
            out = AdminQueuesService.delete_old_tasks_auto()
        return out, get_old_jobs

    def test_the_reapable_ones_are_still_swept(self):
        """The config seen in the field: all seven registries stored, so every
        night raised on `queued` and the three collectable ones were never
        reached."""
        _, get_old_jobs = self._run_auto(ALL_SEVEN)
        assert get_old_jobs.call_args.kwargs["registries"] == REAPABLE

    def test_an_unknown_registry_is_skipped_not_fatal(self):
        _, get_old_jobs = self._run_auto(["finished", "not-a-registry", "failed"])
        assert get_old_jobs.call_args.kwargs["registries"] == ["finished", "failed"]

    def test_nothing_reapable_left_is_a_no_op_not_an_error(self):
        out, get_old_jobs = self._run_auto(["queued", "started"])
        assert out == {"ok": [], "errors": []}
        assert get_old_jobs.call_count == 0

    def test_every_skipped_registry_says_why(self, caplog):
        """The pass degrades silently only if we let it: each dropped entry
        names itself and the config field to correct."""
        with caplog.at_level(logging.WARNING):
            self._run_auto(ALL_SEVEN)
        warnings = "\n".join(
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        )
        for skipped in NON_REAPABLE_REGISTRIES:
            assert skipped in warnings
        assert "old_tasks.queue_registries" in warnings

    def test_the_reapable_ones_are_not_warned_about(self, caplog):
        with caplog.at_level(logging.WARNING):
            self._run_auto(REAPABLE)
        assert caplog.records == []

    def test_the_strict_path_is_unchanged(self):
        """Only the unattended caller works around a bad entry. Anyone asking
        for a live registry explicitly still gets an error."""
        with pytest.raises(Exception):
            AdminQueuesService._get_old_jobs(3600, registries=["queued"])


class TestATerminalJobWithNoEndTimeIsNotImmortal:
    def _job(self, **kwargs):
        stamps = {"ended_at": None, "started_at": None, "created_at": None}
        stamps.update(kwargs)
        return SimpleNamespace(id="j", **stamps)

    def test_ended_at_wins_when_there_is_one(self):
        ended = _ago(days=30)
        job = self._job(ended_at=ended, started_at=_ago(days=90))
        assert AdminQueuesService._reap_reference_time(job, True) == ended.timestamp()

    def test_a_live_registry_gets_no_fallback(self):
        """The original guard, kept where it means something: a job that could
        still be running is skipped, whatever else it carries."""
        job = self._job(started_at=_ago(days=90), created_at=_ago(days=91))
        assert AdminQueuesService._reap_reference_time(job, False) is None

    def test_a_terminal_job_falls_back_to_started_at(self):
        started = _ago(days=90)
        job = self._job(started_at=started, created_at=_ago(days=91))
        assert AdminQueuesService._reap_reference_time(job, True) == started.timestamp()

    def test_a_terminal_job_falls_back_to_created_at(self):
        """A cancelled job never ran, so it has neither an end nor a start."""
        created = _ago(days=91)
        job = self._job(created_at=created)
        assert AdminQueuesService._reap_reference_time(job, True) == created.timestamp()

    def test_a_job_with_no_timestamps_at_all_is_still_skipped(self):
        assert AdminQueuesService._reap_reference_time(self._job(), True) is None


class TestTheSweepCollectsWhatItShould:
    def _sweep(self, job, registries=("failed",)):
        with (
            patch.object(
                AdminQueuesService, "_get_all_queue_job_ids", return_value=[job.id]
            ),
            patch(
                "api.services.admin.queues.Queue.all",
                return_value=[SimpleNamespace(name="storage.default.reclaim")],
            ),
            patch("api.services.admin.queues.Job.fetch_many", return_value=[job]),
        ):
            return AdminQueuesService._get_old_jobs(
                3600, rtype="id", registries=list(registries)
            )

    def _job(self, **kwargs):
        stamps = {"ended_at": None, "started_at": None, "created_at": None}
        stamps.update(kwargs)
        return SimpleNamespace(id="abandoned", **stamps)

    def test_an_abandoned_failed_job_is_reaped(self):
        """rq's `StartedJobRegistry` cleanup moves a job whose worker died to
        `failed` without an `ended_at`. Ten months later it is still there."""
        job = self._job(started_at=_ago(days=300), created_at=_ago(days=300))
        assert self._sweep(job) == ["abandoned"]

    def test_a_job_that_stopped_recently_survives(self):
        job = self._job(started_at=_ago(minutes=5), created_at=_ago(minutes=6))
        assert self._sweep(job) == []

    def test_a_job_that_cannot_be_dated_survives(self):
        assert self._sweep(self._job()) == []
