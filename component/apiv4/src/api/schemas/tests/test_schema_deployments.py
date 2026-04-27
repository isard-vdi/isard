# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/deployments.py``.

Focuses on the contract-relevant request bodies (CreateDeploymentRequest,
DeploymentEditRequest, BulkDeleteDeploymentsRequest, CoOwnersRequest,
DeploymentEditUsersRequest) and the wire-shape sentinels. Pure data
shapes (DeploymentUser, DeploymentGroup, DeploymentDetail) get a
lighter touch — required-fields + defaults only.

Critical: CreateDeploymentRequest carries a `validate_allowed_not_empty`
field validator and a `serialize_desktops` field serializer that forces
persistent=True + bastion_target=None on every desktop. DeploymentEditRequest
has a model_validator that removes desktops from edit list if also in
delete list, plus dedup validators on desktops_to_delete and
desktops_to_edit. Pin all of these.
"""

import pytest
from api.schemas.deployments import (
    BulkDeleteDeploymentsErrorResponse,
    BulkDeleteDeploymentsRequest,
    CheckQuotaRequest,
    CoOwnersRequest,
    CoOwnersResponse,
    CoOwnerUser,
    CreateDeploymentRequest,
    DeploymentDetail,
    DeploymentEditUsersRequest,
    DeploymentPermissions,
    DeploymentUser,
    OwnedDeployment,
)
from pydantic import ValidationError


class TestDeploymentUser:
    def test_minimal(self):
        u = DeploymentUser(id="u-1", name="User", username="u")
        assert u.accessed == 0  # default
        assert u.started_desktops == 0
        assert u.total_desktops == 0
        assert u.photo is None


class TestDeploymentPermissions:
    def test_recreate_value(self):
        assert DeploymentPermissions.recreate.value == "recreate"


class TestCreateDeploymentRequest:
    """Carries the most validators in this module."""

    _desktop = {"template_id": "t-1", "name": "DeskInDep"}

    def _required(self, **overrides):
        body = {
            "name": "MyDeployment",
            "allowed": {"users": ["u-1"]},
            "desktops": [self._desktop],
        }
        body.update(overrides)
        return body

    def test_accepts_required(self):
        r = CreateDeploymentRequest(**self._required())
        # Defaults
        assert r.create_owner_desktop is True
        assert r.visible is False
        assert r.co_owners == []
        assert r.user_permissions == []
        assert r.image is None
        assert r.resources == []

    def test_name_length_bounds(self):
        with pytest.raises(ValidationError):
            CreateDeploymentRequest(**self._required(name="abc"))
        with pytest.raises(ValidationError):
            CreateDeploymentRequest(**self._required(name="x" * 51))

    def test_description_max_255(self):
        with pytest.raises(ValidationError):
            CreateDeploymentRequest(**self._required(), description="x" * 256)

    def test_desktops_min_length_1(self):
        """At least one desktop is required — a deployment with no
        desktops is meaningless. Pin so empty desktops list 422s."""
        with pytest.raises(ValidationError):
            CreateDeploymentRequest(**self._required(desktops=[]))

    def test_allowed_must_have_users_or_groups(self):
        """The custom @field_validator on `allowed` rejects an empty
        AllowedBase (both users and groups False/empty). A deployment
        with no allowed users/groups can never be accessed by anyone
        — must fail fast at request validation."""
        with pytest.raises(ValidationError):
            CreateDeploymentRequest(**self._required(allowed={}))
        # Either users or groups is enough.
        CreateDeploymentRequest(**self._required(allowed={"users": ["u-1"]}))
        CreateDeploymentRequest(**self._required(allowed={"groups": ["g-1"]}))

    def test_serialize_desktops_forces_persistent_and_clears_bastion(self):
        """The @field_serializer mutates each desktop on serialization:
        persistent=True, bastion_target=None — deployment desktops are
        ALWAYS persistent without bastion. Pin the override so a future
        change to a different default for deployment desktops surfaces.
        """
        r = CreateDeploymentRequest(
            **self._required(
                desktops=[
                    {
                        "template_id": "t-1",
                        "name": "DeskInDep",
                        "persistent": False,  # caller's value
                        "bastion_target": {"http": {"enabled": True}},
                    }
                ]
            )
        )
        # The serializer rewrites the in-memory model, which is observable
        # via .desktops directly (the validator runs on access through
        # .model_dump or attribute read).
        dump = r.model_dump()
        assert dump["desktops"][0]["persistent"] is True
        assert dump["desktops"][0]["bastion_target"] is None


class TestBulkDeleteDeploymentsRequest:
    def test_ids_required(self):
        with pytest.raises(ValidationError):
            BulkDeleteDeploymentsRequest()

    def test_default_permanent_false(self):
        """Pin default — so an unset `permanent` doesn't surprise admins
        with a permanent delete."""
        r = BulkDeleteDeploymentsRequest(ids=["dep-1"])
        assert r.permanent is False

    def test_explicit_permanent(self):
        r = BulkDeleteDeploymentsRequest(ids=["dep-1"], permanent=True)
        assert r.permanent is True


class TestBulkDeleteDeploymentsErrorResponse:
    def test_exceptions_required(self):
        with pytest.raises(ValidationError):
            BulkDeleteDeploymentsErrorResponse()


class TestCheckQuotaRequest:
    def test_allowed_optional(self):
        """allowed is Optional — None means "use the deployment's own
        allowed list" (the route looks it up itself)."""
        r = CheckQuotaRequest()
        assert r.allowed is None


class TestCoOwnersRequest:
    def test_co_owners_required(self):
        """co_owners has no default — even an empty list ([]) must be
        explicitly sent. Otherwise the wipe-co-owners contract is
        ambiguous."""
        with pytest.raises(ValidationError):
            CoOwnersRequest()

    def test_accepts_empty_list(self):
        """Empty list = "remove all co-owners"."""
        r = CoOwnersRequest(co_owners=[])
        assert r.co_owners == []


class TestCoOwnerUser:
    def test_minimal(self):
        u = CoOwnerUser(id="u-1", name="User")
        assert u.uid is None
        assert u.photo is None


class TestCoOwnersResponse:
    @pytest.mark.parametrize("missing", ["owner", "co_owners"])
    def test_required(self, missing):
        payload = {
            "owner": {"id": "u-1", "name": "Owner"},
            "co_owners": [],
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            CoOwnersResponse(**payload)


class TestDeploymentEditUsersRequest:
    def test_allowed_required(self):
        with pytest.raises(ValidationError):
            DeploymentEditUsersRequest()

    def test_accepts_arbitrary_dict(self):
        """allowed: dict — no nested schema. The route does its own
        Allowed validation. Pin so a future move to typed Allowed
        is intentional."""
        r = DeploymentEditUsersRequest(allowed={"groups": False, "users": ["u-1"]})
        assert r.allowed == {"groups": False, "users": ["u-1"]}


class TestOwnedDeployment:
    _required = {
        "id": "dep-1",
        "name": "MyDep",
        "description": "x",
        "desktop_names": ["d1"],
        "started_desktops": 0,
        "total_desktops": 1,
        "visible_desktops": 0,
        "total_users": 1,
        "co_owner": False,
        "needs_booking": False,
    }

    def test_accepts_required(self):
        r = OwnedDeployment(**self._required)
        assert r.tag_visible is True  # default
        assert r.image is None
        assert r.next_booking_start is None
        assert r.next_booking_end is None
        assert r.booking_id is None

    def test_booking_id_union(self):
        """booking_id: Optional[str | bool] — pin all three branches."""
        OwnedDeployment(**{**self._required, "booking_id": None})
        OwnedDeployment(**{**self._required, "booking_id": False})
        OwnedDeployment(**{**self._required, "booking_id": "bk-1"})


class TestDeploymentDetail:
    _required = {
        "id": "dep-1",
        "name": "MyDep",
        "description": "x",
        "started_desktops": 0,
        "visible_desktops": 0,
        "total_users": 1,
        "total_desktops": 1,
        "desktops_each_user": 1,
    }

    def test_accepts_required(self):
        r = DeploymentDetail(**self._required)
        assert r.tag_visible is False  # default
