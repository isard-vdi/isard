#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared Pydantic schemas for the usage subsystem.

The retention model is consumed by both apiv4 (request/response
validation on ``/admin/usage/retention``) and the offline rollup
script (to load the live policy from the ``config`` table). Keeping
it in ``_common/schemas/`` makes the contract one source of truth.
"""

from typing import Optional

from pydantic import BaseModel, Field


class UsageRetentionConfig(BaseModel):
    """Tiered retention policy for ``usage_consumption``.

    Daily rows are kept untouched for ``daily_months`` months. Rows
    aged between ``daily_months`` and ``weekly_months`` collapse into
    weekly buckets (Monday-of-week, summed ``inc``, last ``abs`` of
    the bucket). Older rows collapse into monthly buckets (first-of-
    month, same aggregation). When ``total_months`` is set, anything
    older is deleted; when unset, monthly history is retained
    indefinitely.

    Per-field bounds are enforced by Pydantic. The cross-field
    invariants ``weekly_months > daily_months`` and (when set)
    ``total_months >= weekly_months`` are enforced at the route /
    service boundary via :meth:`assert_tier_ordering`. They are NOT
    a ``model_validator`` because raising a ``ValueError`` from one
    propagates a ``RequestValidationError`` whose ``ctx['error']``
    holds the raw ``ValueError``, and the project's global handler
    serialises ``exc.errors()`` to JSON — non-serialisable types in
    ``ctx`` would crash the handler with a 500.
    """

    daily_months: int = Field(
        default=3,
        ge=1,
        le=120,
        description="Months of recent daily granularity to keep untouched.",
    )
    weekly_months: int = Field(
        default=6,
        ge=2,
        le=120,
        description="Months from now until rows collapse from weekly to monthly.",
    )
    total_months: Optional[int] = Field(
        default=None,
        ge=1,
        le=240,
        description=(
            "Hard cap. Rows older than this are deleted. ``None`` keeps "
            "all aggregated history."
        ),
    )

    def assert_tier_ordering(self) -> None:
        """Raise ``ValueError`` when the tier thresholds are inverted.

        Service-layer call sites should invoke this before persisting
        a payload received from the API. The route handler turns the
        ``ValueError`` into a typed 400 ``Error("bad_request")``.
        """
        if self.weekly_months <= self.daily_months:
            raise ValueError("weekly_months must be greater than daily_months")
        if self.total_months is not None and self.total_months < self.weekly_months:
            raise ValueError(
                "total_months, when set, must be greater than or equal to "
                "weekly_months"
            )
