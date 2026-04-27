# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lock FakeRow's additional_properties behaviour against real generated Row models."""

from changefeed_models.bookings_row import BookingsRow
from changefeed_models.domains_row import DomainsRow
from changefeed_models.hypervisors_row import HypervisorsRow
from changefeed_models.media_row import MediaRow
from changefeed_models.users_row import UsersRow
from isardvdi_change_handler.tests.conftest import FakeRow


def test_fakerow_matches_mediarow_additional_properties():
    real = MediaRow.model_validate(
        {
            "id": "m-1",
            "unknown_extra": "x",
        }
    )
    fake = FakeRow(
        id="m-1",
        additional_properties={"unknown_extra": "x"},
    )
    assert real.additional_properties == fake.additional_properties


def test_fakerow_matches_domainsrow_additional_properties():
    real = DomainsRow.model_validate(
        {
            "id": "d-1",
            "unknown_extra": "x",
        }
    )
    fake = FakeRow(
        id="d-1",
        additional_properties={"unknown_extra": "x"},
    )
    assert real.additional_properties == fake.additional_properties


def test_fakerow_matches_usersrow_additional_properties():
    real = UsersRow.model_validate(
        {
            "id": "u-1",
            "unknown_extra": "x",
        }
    )
    fake = FakeRow(
        id="u-1",
        additional_properties={"unknown_extra": "x"},
    )
    assert real.additional_properties == fake.additional_properties


def test_fakerow_matches_bookingsrow_additional_properties():
    real = BookingsRow.model_validate(
        {
            "id": "b-1",
            "unknown_extra": "x",
        }
    )
    fake = FakeRow(
        id="b-1",
        additional_properties={"unknown_extra": "x"},
    )
    assert real.additional_properties == fake.additional_properties


def test_fakerow_matches_hypervisorsrow_additional_properties():
    real = HypervisorsRow.model_validate(
        {
            "id": "h-1",
            "unknown_extra": "x",
        }
    )
    fake = FakeRow(
        id="h-1",
        additional_properties={"unknown_extra": "x"},
    )
    assert real.additional_properties == fake.additional_properties
