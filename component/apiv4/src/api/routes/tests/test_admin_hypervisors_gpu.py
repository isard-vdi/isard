"""Route tests for the GPU lifecycle endpoints ported from upstream MR
!4496 (apiv3 ``/api/v3/hypervisor/<id>/gpu_applied`` and
``/api/v3/admin/gpu/<card_id>/force_profile_preview``).

Real service + twin code paths via the MockThink-backed ``test_client``
(B9): only the DB boundary is mocked.
"""

from api.routes.tests.helpers import MockJWT

# ─── PUT /admin/item/hypervisor/{hyper_id}/gpu_applied ───────────────────


def test_gpu_applied_establishes_passthrough_row(test_client):
    """First-discovery noop on a passthrough-only card whose vgpus row
    exists but carries no vgpu_profile yet: the report establishes the
    passthrough profile + minted pool (update path) instead of leaving the
    card with "no active profile" forever. (The row-insert variant of the
    same branch uses a conflict-lambda insert that rethinkdb_mock cannot
    rewrite, so the route test pins the update arm.)"""
    jwt = MockJWT()

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/gpu_applied",
        method="PUT",
        body={
            "applied": {
                "0000:3b:00.0": {
                    "result": "noop",
                    "applied_profile": "passthrough",
                }
            }
        },
        jwt=jwt,
        db_tables_data={
            "hypervisors": [{"id": "hyper-1"}],
            "vgpus": [{"id": "hyper-1-pci_0000_3b_00_0", "hyp_id": "hyper-1"}],
        },
    )

    assert response.status_code == 204


def test_gpu_applied_ignores_non_dict_reports(test_client):
    """Malformed per-card entries are skipped (the twin tolerates them);
    the endpoint still returns 204 — mirrors apiv3 best-effort semantics."""
    jwt = MockJWT()

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/gpu_applied",
        method="PUT",
        body={"applied": {"0000:3b:00.0": "bogus"}},
        jwt=jwt,
        db_tables_data={"hypervisors": [{"id": "hyper-1"}], "vgpus": []},
    )

    assert response.status_code == 204


def test_gpu_applied_rejects_non_dict_applied(test_client):
    """``applied`` is typed ``Dict[str, Any]`` — a JSON string body is a
    validation error (400 in this app) at the schema layer (apiv3 parsed
    request.form JSON manually)."""
    jwt = MockJWT()

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/gpu_applied",
        method="PUT",
        body={"applied": "not-a-dict"},
        jwt=jwt,
        db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
    )

    assert response.status_code == 400


def test_gpu_applied_requires_admin_or_hypervisor_role(test_client):
    jwt = MockJWT(role_id="user")

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/gpu_applied",
        method="PUT",
        body={"applied": {}},
        jwt=jwt,
        db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
    )

    assert response.status_code == 403


# ─── POST /admin/item/hypervisor/gpus/{card_id}/force_profile_preview ────


def _gpu_tables():
    """One A40 card realizing 4Q with a running desktop; no other card
    realizes the 4Q reservable."""
    return {
        "gpus": [
            {
                "id": "card-1",
                "brand": "NVIDIA",
                "model": "A40",
                "physical_device": "hyper-1-pci_0000_3b_00_0",
                "profiles_enabled": ["NVIDIA-A40-4Q"],
            }
        ],
        "vgpus": [
            {
                "id": "hyper-1-pci_0000_3b_00_0",
                "hyp_id": "hyper-1",
                "vgpu_profile": "4Q",
                "info": {"types": {}},
                "mdevs": {
                    "4Q": {
                        "uuid-1": {
                            "pci_mdev_id": "0000:3b:00.0",
                            "type_id": "nvidia-565",
                            "created": True,
                            "domain_started": "desktop-1",
                            "domain_reserved": False,
                        }
                    }
                },
            }
        ],
    }


def test_force_profile_preview_reports_stops_and_removals(test_client):
    """Forcing the only 4Q-realizing card to passthrough must stop the
    running desktop and remove the now-unrealizable 4Q reservable."""
    jwt = MockJWT(role_id="admin")

    response = test_client(
        url="/admin/item/hypervisor/gpus/card-1/force_profile_preview",
        method="POST",
        body={"target_profile": "NVIDIA-A40-passthrough"},
        jwt=jwt,
        db_tables_data=_gpu_tables(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_profile"] == "4Q"
    assert data["target_profile"] == "passthrough"
    assert data["desktops_to_stop"] == ["desktop-1"]
    assert data["resources_to_remove"] == ["NVIDIA-A40-4Q"]


def test_force_profile_preview_same_profile_is_noop(test_client):
    """Targeting the profile the card already realizes stops nothing and
    removes nothing."""
    jwt = MockJWT(role_id="admin")

    response = test_client(
        url="/admin/item/hypervisor/gpus/card-1/force_profile_preview",
        method="POST",
        body={"target_profile": "NVIDIA-A40-4Q"},
        jwt=jwt,
        db_tables_data=_gpu_tables(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["desktops_to_stop"] == []
    assert data["resources_to_remove"] == []


def test_force_profile_preview_unknown_card_is_empty(test_client):
    """Unknown card: empty preview; the optional current/target fields are
    dropped from the body (response_model_exclude_none)."""
    jwt = MockJWT(role_id="admin")

    response = test_client(
        url="/admin/item/hypervisor/gpus/missing-card/force_profile_preview",
        method="POST",
        body={"target_profile": "NVIDIA-A40-4Q"},
        jwt=jwt,
        db_tables_data={"gpus": [], "vgpus": []},
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {"desktops_to_stop": [], "resources_to_remove": []}


def test_force_profile_preview_requires_target_profile(test_client):
    """Missing target_profile is a validation error (400 in this app) at
    the schema layer (apiv3 raised bad_request manually)."""
    jwt = MockJWT(role_id="admin")

    response = test_client(
        url="/admin/item/hypervisor/gpus/card-1/force_profile_preview",
        method="POST",
        body={"bogus": True},
        jwt=jwt,
        db_tables_data=_gpu_tables(),
    )

    assert response.status_code == 400
