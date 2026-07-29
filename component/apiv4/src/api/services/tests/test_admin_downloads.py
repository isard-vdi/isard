# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminDownloadsService._format_domains.

Two behaviours are locked in here:

1. ``disk_bus`` resolution: the upstream IsardVDI registry puts
   authoritative disk metadata in a sibling top-level ``hardware`` field,
   not inside ``create_dict.hardware.disks``. ``_format_domains`` copies
   ``bus`` across so the engine does not fall back to the hardcoded
   virtio default.
2. XML-driven protection hints: the engine overwrites ``<cpu>``,
   ``<interface>``, and ``<video>`` sections at start-time unless told
   otherwise. ``_format_domains`` inspects the registry XML and sets
   ``not_change_cpu_section`` + ``xml_protected_sections`` so older
   guests (TetrOS-style kvm32 + rtl8139) keep the drivers they shipped.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.schemas.admin.downloads import (
    _REGISTRY_ONLY_DOMAIN_KEYS,
    _REGISTRY_ONLY_MEDIA_KEYS,
    RegistryDomainEntry,
    RegistryMediaEntry,
)
from api.services.admin.downloads import (
    AdminDownloadsService,
    _registry_rejection,
    _servable_entries,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.domain import DomainModel
from isardvdi_common.models.media import MediaModel
from isardvdi_common.schemas.domains import DomainKindEnum

TETROS_XML = """
<domain type='kvm'>
  <name>tetros</name>
  <os><type arch='x86_64' machine='pc'>hvm</type></os>
  <cpu mode='custom' match='exact' check='partial'>
    <model fallback='allow'>kvm32</model>
  </cpu>
  <devices>
    <interface type='network'>
      <mac address='52:54:00:aa:bb:cc'/>
      <source network='default'/>
      <model type='rtl8139'/>
    </interface>
    <video>
      <model type='vga' vram='16384' heads='1' primary='yes'/>
    </video>
  </devices>
</domain>
""".strip()


def _media_entry(**overrides):
    """One ``media`` entry shaped as the updates registry serves it."""
    entry = {
        "id": "b6b1a1f0-0000-4000-8000-000000000001",
        "name": "Virtio ISO drivers",
        "description": "virtio drivers as an ISO image",
        "kind": "iso",
        "icon": "fa-circle-o",
        "url-isard": "virtio-win.iso",
        "url-web": False,
        "default-virtio-iso": True,
        "hypervisors_pools": ["default"],
    }
    entry.update(overrides)
    return entry


def _registry_entry(cd_bus=None, top_bus=None, xml=None, **overrides):
    """Build a registry entry shaped like the upstream /get/domains/list payload."""
    cd_disk = {"file": "x.qcow2", "parent": ""}
    if cd_bus is not None:
        cd_disk["bus"] = cd_bus

    entry = {
        "id": "downloaded_example",
        "name": "Example",
        "create_dict": {
            "hardware": {
                "boot_order": ["disk"],
                "disks": [cd_disk],
                "graphics": ["default"],
                "interfaces": ["default"],
                "memory": 1024,
                "vcpus": 1,
                "videos": ["vga"],
            },
            "hypervisors_pools": ["default"],
        },
        "url-isard": "example.qcow2",
    }
    if top_bus is not None:
        entry["hardware"] = {"disks": [{"bus": top_bus, "dev": "hda"}]}
    if xml is not None:
        entry["xml"] = xml
    entry["kind"] = "desktop"
    entry.update(overrides)
    return entry


def _run_format(entry):
    """Call _format_domains with the heavy external hooks stubbed out."""

    # _get_domain_if_already_downloaded: identity + pop as the real impl does,
    # so the test mirrors production where the top-level "hardware" field is
    # dropped by the time disk_bus resolution runs.
    def fake_already_downloaded(data, _user_id):
        for key in (
            "hardware",
            "xml_to_start",
            "hardware_from_xml",
            "force_update",
            "last_hyp_id",
        ):
            data.pop(key, None)
        return data

    with patch.object(
        AdminDownloadsService,
        "_get_domain_if_already_downloaded",
        side_effect=fake_already_downloaded,
    ), patch.object(
        AdminDownloadsService,
        "_get_user_data",
        return_value={
            "user": "u",
            "username": "u",
            "category": "c",
            "group": "g",
        },
    ), patch(
        "api.services.cards.CardService.get_domain_stock_card",
        return_value="stock.png",
    ), patch(
        "isardvdi_common.helpers.helpers.Helpers.gen_random_mac",
        return_value="52:54:00:00:00:01",
    ), patch(
        "isardvdi_common.helpers.isard_viewer.default_guest_properties",
        return_value={},
    ):
        return AdminDownloadsService._format_domains([entry], "user-id")[0]


class TestFormatDomainsDiskBus:
    def test_pulls_bus_from_sibling_hardware_when_create_dict_missing(self):
        """TetrOS-style entry: cd.hardware.disks[0] has no bus, sibling does."""
        entry = _registry_entry(cd_bus=None, top_bus="ide")
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["disk_bus"] == "ide"

    def test_create_dict_bus_wins_over_sibling(self):
        """If cd.hardware carries an explicit bus, prefer it over the sibling."""
        entry = _registry_entry(cd_bus="sata", top_bus="ide")
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["disk_bus"] == "sata"

    def test_no_disk_bus_key_when_both_sources_absent(self):
        """With neither source set, do not inject a disk_bus — let engine default."""
        entry = _registry_entry(cd_bus=None, top_bus=None)
        result = _run_format(entry)
        assert "disk_bus" not in result["create_dict"]["hardware"]

    def test_virtio_path_unchanged(self):
        """Debian/Ubuntu-style entry with virtio in both fields still lands on virtio."""
        entry = _registry_entry(cd_bus=None, top_bus="virtio")
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["disk_bus"] == "virtio"


class TestParseXmlProtectionHints:
    def test_tetros_xml_flags_all_three_sections(self):
        hints = AdminDownloadsService._parse_xml_protection_hints(TETROS_XML)
        assert hints["not_change_cpu_section"] is True
        assert set(hints["protected_sections"]) == {"cpu", "interface", "video"}

    def test_host_model_cpu_leaves_cpu_alone(self):
        """Host-model is exactly what the engine's override would install, so
        there is nothing to protect and the engine override is harmless."""
        xml = (
            "<domain type='kvm'>"
            "<cpu mode='host-model'><model fallback='allow'/></cpu>"
            "<devices/>"
            "</domain>"
        )
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert hints["not_change_cpu_section"] is False
        assert "cpu" not in hints["protected_sections"]

    def test_host_passthrough_cpu_leaves_cpu_alone(self):
        xml = (
            "<domain type='kvm'>"
            "<cpu mode='host-passthrough'/>"
            "<devices/>"
            "</domain>"
        )
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert hints["not_change_cpu_section"] is False
        assert "cpu" not in hints["protected_sections"]

    def test_interface_without_model_not_protected(self):
        xml = (
            "<domain type='kvm'>"
            "<devices>"
            "<interface type='network'><source network='default'/></interface>"
            "</devices>"
            "</domain>"
        )
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert "interface" not in hints["protected_sections"]

    def test_video_without_model_not_protected(self):
        xml = "<domain type='kvm'><devices><video/></devices></domain>"
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert "video" not in hints["protected_sections"]

    def test_empty_xml_returns_empty_hints(self):
        hints = AdminDownloadsService._parse_xml_protection_hints("")
        assert hints == {"not_change_cpu_section": False, "protected_sections": []}

    def test_malformed_xml_does_not_raise(self):
        """Registry entries occasionally ship malformed/truncated XML; we
        must fall back to no hints instead of aborting the whole download."""
        hints = AdminDownloadsService._parse_xml_protection_hints("<domain><broken")
        assert hints == {"not_change_cpu_section": False, "protected_sections": []}


class TestFormatDomainsProtectionHints:
    def test_tetros_entry_sets_cpu_and_protection_list(self):
        """Full integration: TetrOS-shaped entry populates both engine gates."""
        entry = _registry_entry(cd_bus=None, top_bus="ide", xml=TETROS_XML)
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["not_change_cpu_section"] is True
        assert set(result["create_dict"]["xml_protected_sections"]) == {
            "cpu",
            "interface",
            "video",
        }

    def test_entry_without_xml_does_not_set_hints(self):
        """Debian-style entry with no registry xml leaves both fields absent
        so the engine keeps its current host-model + rebuild behaviour."""
        entry = _registry_entry(cd_bus=None, top_bus="virtio")
        result = _run_format(entry)
        assert "not_change_cpu_section" not in result["create_dict"]["hardware"]
        assert "xml_protected_sections" not in result["create_dict"]

    def test_host_model_xml_does_not_set_hints(self):
        """A modern guest with host-model CPU and no explicit NIC/video model
        should not opt in to protection — the engine's defaults are fine."""
        xml = (
            "<domain type='kvm'>"
            "<cpu mode='host-model'><model fallback='allow'/></cpu>"
            "<devices/>"
            "</domain>"
        )
        entry = _registry_entry(cd_bus=None, top_bus="virtio", xml=xml)
        result = _run_format(entry)
        assert "not_change_cpu_section" not in result["create_dict"]["hardware"]
        assert "xml_protected_sections" not in result["create_dict"]


class TestRegistryEntryValidation:
    """The gate on what the updates registry publishes.

    A template published with a kind outside the taxonomy created a
    domain row that fell out of every kind-scoped query: its owner never
    saw the desktop, could not delete it, and it kept its disk.
    """

    def test_a_real_entry_is_accepted(self):
        assert _registry_rejection("domains", _registry_entry()) is None

    def test_the_defect_is_refused(self):
        rejection = _registry_rejection("domains", _registry_entry(kind="server"))
        assert rejection is not None
        assert "kind" in rejection

    @pytest.mark.parametrize("kind", ["desktop", "template"])
    def test_both_legal_kinds_are_accepted(self, kind):
        assert _registry_rejection("domains", _registry_entry(kind=kind)) is None

    def test_an_entry_without_a_kind_is_refused(self):
        entry = _registry_entry()
        del entry["kind"]
        assert "kind" in _registry_rejection("domains", entry)

    def test_an_unknown_key_is_refused(self):
        rejection = _registry_rejection("domains", _registry_entry(frobnicate=1))
        assert "frobnicate" in rejection

    @pytest.mark.parametrize("kind", ["domains", "media"])
    def test_the_listings_own_new_flag_is_accepted(self, kind):
        """``new`` is added by our own listing before validation runs — a live
        registry serves neither it nor ``status``. The bulk download path
        selects on it, so forbidding it refused every entry: the listing
        dropped all of them and the download reported success having started
        nothing."""
        entry = _registry_entry() if kind == "domains" else _media_entry()
        entry["new"] = True
        assert _registry_rejection(kind, entry) is None

    @pytest.mark.parametrize("kind", ["domains", "media"])
    def test_every_entry_a_live_registry_publishes_is_servable(self, kind):
        entry = _registry_entry() if kind == "domains" else _media_entry()
        entry["new"] = False
        assert _servable_entries(kind, [entry]) == [entry]

    def test_an_entry_with_no_download_source_is_refused(self):
        entry = _registry_entry()
        entry["url-isard"] = False
        assert "url" in _registry_rejection("domains", entry)

    @pytest.mark.parametrize("drop", ["hypervisors_pools", "hardware"])
    def test_create_dict_members_the_download_indexes_are_required(self, drop):
        entry = _registry_entry()
        del entry["create_dict"][drop]
        assert drop in _registry_rejection("domains", entry)

    def test_interfaces_are_required(self):
        entry = _registry_entry()
        del entry["create_dict"]["hardware"]["interfaces"]
        assert "interfaces" in _registry_rejection("domains", entry)

    def test_media_keeps_its_own_taxonomy(self):
        media = {
            "id": "m",
            "name": "An iso",
            "kind": "iso",
            "url-isard": "x.iso",
            "url-web": False,
        }
        assert _registry_rejection("media", media) is None
        media["kind"] = "server"
        assert "kind" in _registry_rejection("media", media)

    def test_media_may_carry_the_virtio_defaults(self):
        """Four published entries do; rejecting them would break Windows."""
        media = {
            "id": "m",
            "name": "virtio",
            "kind": "iso",
            "url-isard": "x.iso",
            "url-web": False,
            "default-virtio-iso": True,
            "default-virtio-fd": True,
        }
        assert _registry_rejection("media", media) is None

    def test_a_kind_we_do_not_gate_is_left_alone(self):
        assert _registry_rejection("videos", {"anything": True}) is None

    def test_one_bad_entry_does_not_cost_the_others(self):
        good, bad = _registry_entry(), _registry_entry(kind="server")
        assert _servable_entries("domains", [good, bad]) == [good]


class TestRegistryModelsFollowTheRowModels:
    """The accepted keys are derived, not restated.

    If these drift apart, a field added to the row model stops being
    accepted from the registry — which is a template silently vanishing
    from the catalogue, so it fails here instead.
    """

    def test_domain_keys_come_from_the_domain_model(self):
        assert set(RegistryDomainEntry.model_fields) == set(
            DomainModel.model_fields
        ) | {key.replace("-", "_") for key in _REGISTRY_ONLY_DOMAIN_KEYS}

    def test_media_keys_come_from_the_media_model(self):
        assert set(RegistryMediaEntry.model_fields) == set(MediaModel.model_fields) | {
            key.replace("-", "_") for key in _REGISTRY_ONLY_MEDIA_KEYS
        }

    def test_the_domain_kind_is_the_taxonomy(self):
        legal = {
            kind
            for kind in ("desktop", "template", "server", "")
            if _registry_rejection("domains", _registry_entry(kind=kind)) is None
        }
        assert legal == {member.value for member in DomainKindEnum}


class TestRegistryMediaGetsADestination:
    """A registry media row must carry ``path_downloaded`` before it is
    inserted: ``enqueue_download_chain`` refuses without one
    (``media_no_path``), so the row was created and the download never started.
    Reproduced live: the row landed at ``DownloadStarting`` and the request
    answered 428 with "has no path_downloaded; cannot enqueue download".
    """

    def _entry(self):
        return {
            "id": "c0ffee00-0000-4000-8000-00000000beef",
            "name": "Virtio ISO drivers",
            "kind": "iso",
            "url-isard": "virtio-win.iso",
        }

    def test_the_destination_is_resolved(self, monkeypatch):
        from api.services.admin import downloads as mod

        monkeypatch.setattr(
            mod.AdminDownloadsService,
            "_get_media_if_already_downloaded",
            staticmethod(lambda d, user_id: d),
        )
        monkeypatch.setattr(
            mod.AdminDownloadsService,
            "_get_user_data",
            staticmethod(lambda user_id: {"category": "cat1", "user": user_id}),
        )
        import isardvdi_common.models.media as media_mod

        monkeypatch.setattr(
            media_mod.Media,
            "resolve_download_path",
            classmethod(
                lambda cls, user_id, category_id, media_id, kind: (
                    None,
                    f"/isard/media/{media_id}.{kind}",
                )
            ),
        )
        out = mod.AdminDownloadsService._format_medias([self._entry()], "u1")
        assert out[0]["path_downloaded"] == (
            "/isard/media/c0ffee00-0000-4000-8000-00000000beef.iso"
        )

    def test_an_already_downloaded_row_keeps_its_path(self, monkeypatch):
        from api.services.admin import downloads as mod

        entry = self._entry()
        entry["path_downloaded"] = "/isard/media/somewhere-else.iso"
        monkeypatch.setattr(
            mod.AdminDownloadsService,
            "_get_media_if_already_downloaded",
            staticmethod(lambda d, user_id: d),
        )
        monkeypatch.setattr(
            mod.AdminDownloadsService,
            "_get_user_data",
            staticmethod(lambda user_id: {"category": "cat1", "user": user_id}),
        )
        out = mod.AdminDownloadsService._format_medias([entry], "u1")
        assert out[0]["path_downloaded"] == "/isard/media/somewhere-else.iso"


class TestRegistryDownloadSource:
    """``url-isard`` is a path relative to the registry, not a URL. Handed to
    curl as-is it was resolved as a hostname (exit 6, "couldn't resolve host")
    and the row landed ``DownloadFailed`` — verified live. The registry also
    refuses an unauthenticated fetch, so the registration code has to travel
    with it. The domain branch already built this; media did not.
    """

    def _cfg(self, monkeypatch, url="https://repository.example.com", code="abc123"):
        from api.services.admin import downloads as mod

        monkeypatch.setattr(
            mod.AdminDownloadsService,
            "_get_cfg",
            staticmethod(lambda: (url, code, None)),
        )
        return mod.AdminDownloadsService

    def test_a_relative_isard_path_becomes_an_absolute_registry_url(self, monkeypatch):
        svc = self._cfg(monkeypatch)
        url, headers = svc._registry_download_source(
            "media", {"url-isard": "windows-10-optimizer_v1.iso", "url-web": False}
        )
        assert url == (
            "https://repository.example.com/storage/media/"
            "windows-10-optimizer_v1.iso"
        )
        assert headers == ["Authorization: abc123"]

    def test_domains_use_their_own_folder(self, monkeypatch):
        svc = self._cfg(monkeypatch)
        url, _ = svc._registry_download_source(
            "domains", {"url-isard": "some-template.qcow2"}
        )
        assert url.endswith("/storage/domains/some-template.qcow2")

    def test_a_trailing_slash_on_the_configured_url_is_not_doubled(self, monkeypatch):
        svc = self._cfg(monkeypatch, url="https://repository.example.com/")
        url, _ = svc._registry_download_source("media", {"url-isard": "/x.iso"})
        assert url == "https://repository.example.com/storage/media/x.iso"

    def test_url_web_is_absolute_and_carries_no_credentials(self, monkeypatch):
        svc = self._cfg(monkeypatch)
        url, headers = svc._registry_download_source(
            "media", {"url-isard": False, "url-web": "https://elsewhere/x.iso"}
        )
        assert url == "https://elsewhere/x.iso"
        assert headers == []

    def test_an_already_absolute_url_on_the_row_wins(self, monkeypatch):
        svc = self._cfg(monkeypatch)
        url, headers = svc._registry_download_source(
            "media", {"url": "https://direct/x.iso", "url-isard": "x.iso"}
        )
        assert url == "https://direct/x.iso"
        assert headers == []

    def test_no_registration_code_means_no_header(self, monkeypatch):
        svc = self._cfg(monkeypatch, code=None)
        _url, headers = svc._registry_download_source("media", {"url-isard": "x.iso"})
        assert headers == []

class TestDownloadsDeleteAndAbort:
    """The delete button used to write a status and hope.

    Nothing consumed it, the engine's broom rewrote it to ``Unknown``,
    and the storage worker never saw a task — so the row could not be
    deleted at all. These pin that the endpoint now does the work, and
    that it refuses rather than half-doing it.
    """

    def _domain(self, status, kind="desktop", storage_id="s-1"):
        domain = SimpleNamespace(
            id="d-1",
            status=status,
            kind=kind,
            create_dict={"hardware": {"disks": [{"storage_id": storage_id}]}},
        )
        return domain

    def _patched(self, domain, task_pending=False, storage_task="t-1"):
        """Patch everything the action reaches, returning the mocks."""
        storage = SimpleNamespace(task=storage_task)
        return (
            patch(
                "isardvdi_common.models.domain.Domain.exists",
                staticmethod(lambda _id: True),
            ),
            patch(
                "isardvdi_common.models.domain.Domain.__new__",
                lambda cls, *a, **k: domain,
            ),
            patch(
                "isardvdi_common.models.storage.Storage.exists",
                staticmethod(lambda _id: True),
            ),
            patch(
                "isardvdi_common.models.storage.Storage.__new__",
                lambda cls, *a, **k: storage,
            ),
            patch(
                "isardvdi_common.models.task.Task.exists",
                staticmethod(lambda _id: bool(storage_task)),
            ),
            patch(
                "isardvdi_common.models.task.Task.__new__",
                lambda cls, *a, **k: SimpleNamespace(
                    pending=task_pending, cancel=lambda: None
                ),
            ),
        )

    def _run(self, action, domain, task_pending=False, storage_task="t-1"):
        patches = self._patched(domain, task_pending, storage_task)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            with patch(
                "api.services.desktops.DesktopService.delete_desktop"
            ) as delete_desktop:
                result = AdminDownloadsService._domain_action(action, "d-1", "u1")
                return result, delete_desktop

    @pytest.mark.parametrize("status", ["Downloading", "DownloadStarting"])
    def test_deleting_a_running_download_is_refused(self, status):
        with pytest.raises(Error) as raised:
            self._run("delete", self._domain(status))
        assert raised.value.error["description_code"] == "download_in_progress"

    def test_deleting_while_a_task_is_pending_is_refused(self):
        with pytest.raises(Error) as raised:
            self._run("delete", self._domain("Failed"), task_pending=True)
        assert raised.value.error["description_code"] == "download_task_pending"

    def test_a_row_with_an_unsupported_kind_is_refused(self):
        with pytest.raises(Error) as raised:
            self._run("delete", self._domain("Unknown", kind="server"))
        assert raised.value.error["description_code"] == "download_row_unsupported_kind"

    @pytest.mark.parametrize("status", ["Stopped", "Failed", "Unknown", "Deleting"])
    def test_a_settled_row_is_really_deleted(self, status):
        """Including the states the old code left stranded."""
        _result, delete_desktop = self._run("delete", self._domain(status))
        delete_desktop.assert_called_once()
        assert delete_desktop.call_args.kwargs["permanent"] is True

    def test_aborting_what_is_not_running_is_refused(self):
        with pytest.raises(Error) as raised:
            self._run("abort", self._domain("Stopped"))
        assert raised.value.error["description_code"] == "download_not_running"

    def test_aborting_a_live_download_asks_the_task_to_stop(self):
        domain = self._domain("Downloading")
        self._run("abort", domain, task_pending=True)
        assert domain.status == "DownloadAborting"

    def test_aborting_with_nothing_running_settles_the_row(self):
        """Otherwise it sits at DownloadAborting for good."""
        domain = self._domain("DownloadAborting")
        self._run("abort", domain, task_pending=False, storage_task=None)
        assert domain.status == "Failed"

    def test_media_delete_goes_through_the_media_service(self):
        with patch("api.services.media.MediaService.delete_media") as delete_media:
            delete_media.return_value = "task-7"
            result = AdminDownloadsService._media_action("delete", "m-1", "u1")
        delete_media.assert_called_once_with("m-1", {"user_id": "u1"})
        assert result["task_id"] == "task-7"

    def test_media_abort_goes_through_the_media_service(self):
        with patch("api.services.media.MediaService.abort_media_download") as abort:
            AdminDownloadsService._media_action("abort", "m-1", "u1")
        abort.assert_called_once_with("m-1")
