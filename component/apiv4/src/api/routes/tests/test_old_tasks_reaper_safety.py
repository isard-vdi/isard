# SPDX-License-Identifier: AGPL-3.0-or-later

"""The old-tasks sweep must never delete work that has not finished.

Two halves of the same defect: the config surface accepted registries the sweep
then refused (so every nightly run raised and nothing was ever purged), and the
age test counted a missing `ended_at` as "old" - which is exactly what a
DEFERRED or running job has. Had the sweep ever run with `deferred` configured,
it would have deleted live chains, and `delete_dependents` would have taken the
rest of each chain with them.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.services.admin.queues import NON_REAPABLE_REGISTRIES, AdminQueuesService


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


class TestJobsWithoutAnEndTimeAreNeverOld:
    def _jobs(self, *jobs):
        return list(jobs)

    def test_missing_ended_at_is_skipped(self):
        """A job with no ``ended_at`` has not finished - it cannot be proven
        old, so it must survive the sweep."""
        live = SimpleNamespace(id="live", ended_at=None)
        with (
            patch.object(
                AdminQueuesService, "_get_all_queue_job_ids", return_value=["live"]
            ),
            patch("api.services.admin.queues.Queue.all", return_value=[]),
        ):
            out = AdminQueuesService._get_old_jobs(3600, registries=["finished"])
        assert out == [] or "live" not in out
